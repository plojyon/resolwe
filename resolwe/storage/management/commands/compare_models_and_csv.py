""".. Ignore pydocstyle D400.

======================
Compare models and CSV
======================

"""
import csv
import logging
import os

from django.core.management.base import BaseCommand
from django.db.models import Q

from resolwe.flow.models import Data
from resolwe.storage.models import ReferencedPath

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Compare Django's Data records with a CSV file and log differences.

    expected CSV format:
        bucket_id, file_key, file_size, file_hash
    """

    help = (
        "Log differences between Data records in models (Django database)"
        " and records from a CSV file (S3 inventory)."
        " Expected CSV format: bucket_id, file_key, file_size, file_hash"
    )

    def add_arguments(self, parser):
        """Add command arguments."""
        # Positional argument: path to CSV file
        parser.add_argument("csv_path", nargs=1, type=str)

    def handle(self, *args, **options):
        """Command handle."""
        CSV = FileIterator(options["csv_path"][0])
        models = Data.objects.all().order_by("location__pk")
        counter = {
            "match": 0,
            "csv_only": 0,
            "models_only": 0,
            "hash_mismatch": 0,
        }
        subpath_map = map_subpath_locations(CSV)

        for data in models.iterator():
            subpath = data.location.subpath
            urls = data.location.files
            urls = urls.exclude(Q(path__endswith="/"))  # exclude directories
            urls = urls.order_by("path")
            URLS = ModelIterator(urls)

            if subpath not in subpath_map:
                filecount = URLS.count
                logger.warning(f"MODEL-ONLY {subpath}/* ({filecount} files)")
                counter["models_only"] += filecount
                continue
            else:
                subpath_map[subpath]["visited"] = True

            CSV.restrict(
                start=subpath_map[subpath]["start"],
                end=subpath_map[subpath]["end"],
            )
            CSV.seek_relative(0)

            next_in_models, model_hash = URLS.next()
            next_in_csv, csv_hash = CSV.next()
            while next_in_csv and next_in_models:
                if next_in_models == next_in_csv:
                    # entries match, verify checksum
                    if model_hash == csv_hash:
                        counter["match"] += 1
                    else:
                        fullpath = f"{subpath}/{next_in_models}"
                        hashes = f"{model_hash} != {csv_hash}"
                        logger.warning(f"HASH {fullpath} {hashes}")
                        counter["hash_mismatch"] += 1
                    # advance both
                    next_in_models, model_hash = URLS.next()
                    next_in_csv, csv_hash = CSV.next()
                elif next_in_models < next_in_csv or not CSV.has_next():
                    # entries are missing in CSV
                    # (models are alphabetically *behind*)
                    fullpath = subpath + "/" + next_in_models
                    logger.warning(f"MODEL-ONLY {fullpath}")
                    counter["models_only"] += 1
                    next_in_models, model_hash = URLS.next()  # advance models
                elif next_in_models > next_in_csv or not URLS.has_next():
                    # entries are missing in models
                    # (models are alphabetically *ahead*)
                    fullpath = subpath + "/" + next_in_csv
                    logger.warning(f"CSV-ONLY {fullpath}")
                    counter["csv_only"] += 1
                    next_in_csv, csv_hash = CSV.next()  # advance CSV

            # either (or both) of the iterators is finished,
            # now we need to exhaust the other
            while next_in_csv:
                logger.warning(f"CSV-ONLY {subpath}/{next_in_csv}")
                counter["csv_only"] += 1
                next_in_csv, csv_hash = CSV.next()
            while next_in_models:
                logger.warning(f"MODEL-ONLY {subpath}/{next_in_models}")
                counter["models_only"] += 1
                next_in_models, model_hash = URLS.next()

        # list all subpaths from CSV that we haven't visited
        # while traversing models' data
        for subpath in subpath_map:
            if "visited" not in subpath_map[subpath]:
                filecount = subpath_map[subpath]["linecount"]
                logger.warning(f"CSV-ONLY {subpath}/* ({filecount} files)")
                counter["csv_only"] += filecount

        # print an overview/summary
        out = ""
        out += f"{counter['match']} files OK"
        if counter["csv_only"] != 0:
            out += f", {counter['csv_only']} files in CSV only"
        if counter["models_only"] != 0:
            out += f", {counter['models_only']} files in models only"
        if counter["hash_mismatch"] != 0:
            out += f", {counter['hash_mismatch']} files do not match the hash"
        logger.info(out)

        # double check the numbers just in case
        ReferencedPath_count = ReferencedPath.objects.exclude(
            Q(path__endswith="/")
        ).count()
        logger.debug(f"CSV length = {CSV.length}")
        logger.debug(f"ReferencedPath object count = {ReferencedPath_count}")

        matches = counter["hash_mismatch"] + counter["match"]
        csv_records = matches + counter["csv_only"]
        models_records = matches + counter["models_only"]
        # this should never happen, but it's better to check,
        # just because it's so easy to do
        if csv_records != CSV.length:
            logger.debug(
                "Numbers don't add up."
                " OK + csv_only + hash_mismatch != CSV.line_count."
            )
        if models_records != ReferencedPath_count:
            logger.debug(
                "Numbers don't add up."
                " OK + models_only + hash_mismatch != ReferencedPath_count."
                " There are probably orphaned ReferencedPaths."
            )


def parseline(line):
    """Parse a line of CSV data into an array of values."""
    reader = csv.reader([line])
    for i in reader:
        return i  # reader will return only one line anyway


def get_filename(line):
    """Extract the name of the file from a line of CSV data.

    If the file has no subpath, the file key will be treated as a subpath name,
    and get_filename will return an empty string.
    """
    key = parseline(line)[1]  # full file key

    # strip subpath
    splits = key.split("/")
    splits.pop(0)
    return "/".join(splits)


def get_subpath(line):
    """Extract the subpath of the file from a line of CSV data.

    If the file has no subpath, the file key will be treated as a subpath name,
    and get_filename will return an empty string.
    """
    columns = parseline(line)
    s3key = columns[1]
    subpath = s3key.split("/")[0]
    return subpath


def get_etag(line):
    """Extract the etag of the file from a line of CSV data."""
    return parseline(line)[3]


def map_subpath_locations(file):
    """Map subpaths to their locations in a CSV file.

    Also count the number of lines for
    each subpath and the file as a whole.

    Sample output:
    ```
    {
        '1': {'start': 0, 'end': 234, 'linecount': 2},
        '100': {'start': 234, 'end': 876516, 'linecount': 7202},
        '101': {'start': 876516, 'end': 877441, 'linecount': 6},
        '86': {'start': 6324115, 'end': 6326268, 'linecount': 17},
        ...
        '94': {'start': 6338834, 'end': 7177568, 'linecount': 6975},
        '98': {'start': 7183154, 'end': 7184069, 'linecount': 6},
        'README': {'start': 7184944, 'end': 7185044, 'linecount': 1}
    }
    ```
    """
    mapping = {}
    last_subpath = -1
    current_subpath_linecount = 0
    file.seek(0)
    total_linecount = 0
    while file.has_next():
        subpath = get_subpath(file.readline())
        if subpath != last_subpath:
            mapping[subpath] = {}
            mapping[subpath]["start"] = file.last_position
            if last_subpath != -1:
                mapping[last_subpath]["end"] = file.last_position
                mapping[last_subpath]["linecount"] = current_subpath_linecount
            last_subpath = subpath
            current_subpath_linecount = 0
        current_subpath_linecount += 1
        total_linecount += 1

    if last_subpath == -1:
        # empty CSV file
        file.length = 0
        return {}

    mapping[last_subpath]["linecount"] = current_subpath_linecount
    mapping[last_subpath]["end"] = file.size
    file.length = total_linecount  # set the line count for further convenience
    return mapping


class FileIterator:
    """An iterator for reading a CSV file within a given range."""

    def __init__(self, csv_filename):
        """Initialize the FileIterator.

        :param csv_filename: The path to the CSV file to be read
        """
        self.name = csv_filename
        self.file = open(self.name, "r")
        self.size = os.fstat(self.file.fileno()).st_size
        self.length = -1  # number of lines (must be set externally)
        self.last_position = 0
        self.restrictions = {"start": 0, "end": self.size}

    def __del__(self):
        """Destruct the object. Close the file."""
        self.file.close()

    def tell(self):
        """Return the current position of the reader."""
        return self.file.tell()

    def seek(self, position):
        """Seek to a given position within the file.

        This may position the reader outside the restriction interval,
        resulting in has_next() always returning False.
        """
        self.last_position = self.tell()
        self.file.seek(position)

    def seek_relative(self, position):
        """Seek to a given position relative to the restriction interval."""
        self.seek(self.restrictions["start"] + position)

    def readline(self):
        """Return the next line of CSV data."""
        self.last_position = self.tell()
        return self.file.readline()

    def next(self):
        """Return the next line's path string and etag.

        If the file has been exhausted (or reached the end of its restriction
        interval), ("", "") is returned.
        """
        if not self.has_next():
            return "", ""

        line = self.readline()
        return get_filename(line), get_etag(line)

    def has_next(self):
        """Check if the file reached the end of its restriction interval."""
        return self.tell() < self.restrictions["end"]

    def restrict(self, start=0, end=-1):
        """Restrict reading to an interval from start to end.

        Call with default parameters to unrestrict.
        """
        if end == -1:
            end = self.size
        self.restrictions = {"start": start, "end": end}


class ModelIterator:
    """An iterator for traversing a QuerySet.

    This is a wrapper with similar methods as the
    FileIterator, to provide nice symmetric-looking code.
    """

    def __init__(self, urls):
        """Initialize the ModelIterator.

        :param urls: A QuerySet of ReferencedPaths, ordered by path.
        """
        self.urls = urls
        self.count = self.urls.count()

        self.urls = [u for u in urls]
        # these should already be *mostly* sorted
        # problem is, SQL sorts "_" before ".",
        # but python does it the other way around
        # so this has to be re-sorted to match the sorting used within the CSV
        self.urls.sort(key=lambda a: a.path)

        self.i = 0

    def next(self):
        """Return the next ReferencedPath's path string and the file's etag.

        If all ReferencedPaths have been exhausted, ("", "") is returned.
        """
        if not self.has_next():
            return "", ""

        next = self.urls[self.i]
        self.i += 1

        return next.path, next.awss3etag

    def has_next(self):
        """Check if all ReferencedPaths have been exhausted."""
        return self.i < self.count
