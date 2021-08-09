import logging
from io import StringIO

from django.core.management import call_command
from django.db.models import Q
from django.test import TestCase

from resolwe.flow.models import Data, Process
from resolwe.storage.management.commands.compare_models_and_csv import (
    FileIterator,
    ModelIterator,
    get_etag,
    get_filename,
    get_subpath,
    map_subpath_locations,
    parseline,
)
from resolwe.storage.models import FileStorage, ReferencedPath, StorageLocation


class CompareModelsTestCase(TestCase):
    def setUp(self):
        self.proc = Process.objects.create(
            contributor_id=1, name="test.process", slug="test_process"
        )
        # subpath 100
        self.fs100 = FileStorage.objects.create()
        self.d100 = Data.objects.create(
            name="test_data100",
            process_id=self.proc.id,
            contributor_id=1,
            location=self.fs100,
        )
        self.sl100 = StorageLocation.objects.create(
            file_storage_id=self.fs100.id, url="100"
        )
        # subpath 123
        self.fs123 = FileStorage.objects.create()
        self.d123 = Data.objects.create(
            name="test_data123",
            process_id=self.proc.id,
            contributor_id=1,
            location=self.fs123,
        )
        self.sl123 = StorageLocation.objects.create(
            file_storage_id=self.fs123.id, url="123"
        )

        self.make_file = lambda name, sl: ReferencedPath.objects.create(
            path=name, awss3etag="hashhashhash"
        ).storage_locations.add(sl)

        # all paths present in csv:
        self.make_file("names/000.json", self.sl100)
        self.make_file("names/001.json", self.sl100)
        self.make_file("names/002.json", self.sl100)
        self.make_file("names/003.json", self.sl100)
        self.make_file("names/004.json", self.sl100)
        self.make_file("names/005.json", self.sl100)

        self.make_file("d.json", self.sl123)
        self.make_file("f.json", self.sl123)
        self.make_file("j.json", self.sl123)
        self.make_file("k.json", self.sl123)
        self.make_file("l.json", self.sl123)

        first_half = "../resolwe/storage/tests"
        second_half = "/files/compare_models_and_csv.csv"
        self.csv_filename = first_half + second_half  # 79ch line length limit

        # redirect logger to a stream
        self.output = StringIO()
        logger = logging.getLogger(
            "resolwe.storage.management.commands.compare_models_and_csv"
        )
        handler = logging.StreamHandler(self.output)
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    def test_complete_match(self):
        call_command("compare_models_and_csv", self.csv_filename)
        self.output = self.output.getvalue()
        self.assertNotIn("CSV-ONLY", self.output)
        self.assertNotIn("MODEL-ONLY", self.output)
        self.assertIn("11 files OK", self.output)
        self.assertNotIn("files in CSV only", self.output)
        self.assertNotIn("files in models only", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_complete_mismatch(self):
        ReferencedPath.objects.all().delete()

        self.make_file("names/006.json", self.sl100)

        self.make_file("a.json", self.sl123)
        self.make_file("b.json", self.sl123)
        self.make_file("c.json", self.sl123)
        self.make_file("e.json", self.sl123)
        self.make_file("g.json", self.sl123)
        self.make_file("h.json", self.sl123)
        self.make_file("i.json", self.sl123)

        call_command("compare_models_and_csv", self.csv_filename)
        self.output = self.output.getvalue()
        self.assertIn("CSV-ONLY 100/names/000.json", self.output)
        self.assertIn("CSV-ONLY 100/names/001.json", self.output)
        self.assertIn("CSV-ONLY 100/names/002.json", self.output)
        self.assertIn("CSV-ONLY 100/names/003.json", self.output)
        self.assertIn("CSV-ONLY 100/names/004.json", self.output)
        self.assertIn("CSV-ONLY 100/names/005.json", self.output)
        self.assertIn("MODEL-ONLY 100/names/006.json", self.output)
        self.assertIn("CSV-ONLY 123/d.json", self.output)
        self.assertIn("CSV-ONLY 123/f.json", self.output)
        self.assertIn("CSV-ONLY 123/j.json", self.output)
        self.assertIn("CSV-ONLY 123/k.json", self.output)
        self.assertIn("CSV-ONLY 123/l.json", self.output)
        self.assertIn("MODEL-ONLY 123/a.json", self.output)
        self.assertIn("MODEL-ONLY 123/b.json", self.output)
        self.assertIn("MODEL-ONLY 123/c.json", self.output)
        self.assertIn("MODEL-ONLY 123/e.json", self.output)
        self.assertIn("MODEL-ONLY 123/g.json", self.output)
        self.assertIn("MODEL-ONLY 123/h.json", self.output)
        self.assertIn("MODEL-ONLY 123/i.json", self.output)
        self.assertIn("0 files OK", self.output)
        self.assertIn("11 files in CSV only", self.output)
        self.assertIn("8 files in models only", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_missing_subpath_in_models(self):
        self.sl100.files.all().delete()
        self.d100.delete()

        call_command("compare_models_and_csv", self.csv_filename)
        self.output = self.output.getvalue()
        self.assertIn("CSV-ONLY 100/* (6 files)", self.output)
        self.assertNotIn("MODEL-ONLY", self.output)
        self.assertIn("5 files OK, 6 files in CSV only", self.output)
        self.assertNotIn("files in models only", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_missing_subpath_in_csv(self):
        # subpath 200
        self.fs200 = FileStorage.objects.create()
        self.d200 = Data.objects.create(
            name="test_data200",
            process_id=self.proc.id,
            contributor_id=1,
            location=self.fs200,
        )
        self.sl200 = StorageLocation.objects.create(
            file_storage_id=self.fs200.id, url="200"
        )

        self.make_file("x.json", self.sl200)
        self.make_file("y.json", self.sl200)
        self.make_file("z.json", self.sl200)

        call_command("compare_models_and_csv", self.csv_filename)
        self.output = self.output.getvalue()
        self.assertIn("MODEL-ONLY 200/* (3 files)", self.output)
        self.assertNotIn("CSV-ONLY", self.output)
        self.assertIn("11 files OK, 3 files in models only", self.output)
        self.assertNotIn("files in CSV only", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_empty_models(self):
        self.sl100.files.all().delete()
        self.d100.delete()
        self.sl123.files.all().delete()
        self.d123.delete()

        call_command("compare_models_and_csv", self.csv_filename)
        self.output = self.output.getvalue()
        self.assertIn("CSV-ONLY 100/* (6 files)", self.output)
        self.assertIn("CSV-ONLY 123/* (5 files)", self.output)
        self.assertNotIn("MODEL-ONLY", self.output)
        self.assertIn("0 files OK, 11 files in CSV only", self.output)
        self.assertNotIn("files in models only", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_empty_csv(self):
        call_command("compare_models_and_csv", "/dev/null")
        self.output = self.output.getvalue()
        self.assertIn("MODEL-ONLY 100/* (6 files)", self.output)
        self.assertIn("MODEL-ONLY 123/* (5 files)", self.output)
        self.assertNotIn("CSV-ONLY", self.output)
        self.assertIn("0 files OK, 11 files in models only", self.output)
        self.assertNotIn("files in CSV only", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_missing_first_file_in_models(self):
        ReferencedPath.objects.get(path="names/000.json").delete()
        ReferencedPath.objects.get(path="names/001.json").delete()
        call_command("compare_models_and_csv", self.csv_filename)
        self.output = self.output.getvalue()
        self.assertIn("CSV-ONLY 100/names/000.json", self.output)
        self.assertIn("CSV-ONLY 100/names/001.json", self.output)
        self.assertNotIn("MODEL-ONLY", self.output)
        self.assertIn("9 files OK, 2 files in CSV only", self.output)
        self.assertNotIn("files in models only", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_missing_last_file_in_models(self):
        ReferencedPath.objects.get(path="names/004.json").delete()
        ReferencedPath.objects.get(path="names/005.json").delete()
        call_command("compare_models_and_csv", self.csv_filename)
        self.output = self.output.getvalue()
        self.assertIn("CSV-ONLY 100/names/004.json", self.output)
        self.assertIn("CSV-ONLY 100/names/005.json", self.output)
        self.assertNotIn("MODEL-ONLY", self.output)
        self.assertIn("9 files OK, 2 files in CSV only", self.output)
        self.assertNotIn("files in models only", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_missing_first_file_in_csv(self):
        self.make_file("a.json", self.sl123)
        self.make_file("b.json", self.sl123)
        self.make_file("c.json", self.sl123)
        call_command("compare_models_and_csv", self.csv_filename)
        self.output = self.output.getvalue()
        self.assertIn("MODEL-ONLY 123/a.json", self.output)
        self.assertIn("MODEL-ONLY 123/b.json", self.output)
        self.assertIn("MODEL-ONLY 123/c.json", self.output)
        self.assertNotIn("CSV-ONLY", self.output)
        self.assertIn("11 files OK, 3 files in models only", self.output)
        self.assertNotIn("files in CSV only", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_missing_last_file_in_csv(self):
        self.make_file("names/006.json", self.sl100)
        self.make_file("m.json", self.sl123)
        call_command("compare_models_and_csv", self.csv_filename)
        self.output = self.output.getvalue()
        self.assertIn("MODEL-ONLY 100/names/006.json", self.output)
        self.assertIn("MODEL-ONLY 123/m.json", self.output)
        self.assertNotIn("CSV-ONLY", self.output)
        self.assertIn("11 files OK, 2 files in models only", self.output)
        self.assertNotIn("files in CSV only", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_missing_middle_file_in_models(self):
        ReferencedPath.objects.get(path="names/002.json").delete()
        ReferencedPath.objects.get(path="names/003.json").delete()
        call_command("compare_models_and_csv", self.csv_filename)
        self.output = self.output.getvalue()
        self.assertIn("CSV-ONLY 100/names/002.json", self.output)
        self.assertIn("CSV-ONLY 100/names/003.json", self.output)
        self.assertNotIn("MODEL-ONLY", self.output)
        self.assertIn("9 files OK, 2 files in CSV only", self.output)
        self.assertNotIn("files in models only", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_missing_middle_file_in_csv(self):
        self.make_file("e.json", self.sl123)
        self.make_file("g.json", self.sl123)
        self.make_file("h.json", self.sl123)
        self.make_file("i.json", self.sl123)
        call_command("compare_models_and_csv", self.csv_filename)
        self.output = self.output.getvalue()
        self.assertIn("MODEL-ONLY 123/e.json", self.output)
        self.assertIn("MODEL-ONLY 123/g.json", self.output)
        self.assertIn("MODEL-ONLY 123/h.json", self.output)
        self.assertIn("MODEL-ONLY 123/i.json", self.output)
        self.assertNotIn("CSV-ONLY", self.output)
        self.assertIn("11 files OK, 4 files in models only", self.output)
        self.assertNotIn("files in CSV only", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_partial_mismatch(self):
        # Situation like this:
        # CSV | models
        #  0      0  (start with a match)
        #  1         (models leading)
        #  2         (no common entry for them to meet)
        #         25 (CSV starts to lead)
        #  3
        #         35 (mismatching entries)
        #  4
        #  5      5  (finish with another match)
        self.make_file("names/0025.json", self.sl100)
        self.make_file("names/0035.json", self.sl100)
        ReferencedPath.objects.get(path="names/001.json").delete()
        ReferencedPath.objects.get(path="names/002.json").delete()
        ReferencedPath.objects.get(path="names/003.json").delete()
        ReferencedPath.objects.get(path="names/004.json").delete()
        call_command("compare_models_and_csv", self.csv_filename)
        self.output = self.output.getvalue()
        self.assertIn("MODEL-ONLY 100/names/0025.json", self.output)
        self.assertIn("MODEL-ONLY 100/names/0035.json", self.output)
        self.assertIn("CSV-ONLY 100/names/001.json", self.output)
        self.assertIn("CSV-ONLY 100/names/002.json", self.output)
        self.assertIn("CSV-ONLY 100/names/003.json", self.output)
        self.assertIn("CSV-ONLY 100/names/004.json", self.output)
        self.assertIn("7 files OK", self.output)
        self.assertIn("2 files in models only", self.output)
        self.assertIn("4 files in CSV only", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_partial_mismatch_no_common_finish(self):
        # same as test_partial_mismatch, but without the common finish
        self.make_file("names/0025.json", self.sl100)
        self.make_file("names/0035.json", self.sl100)
        ReferencedPath.objects.get(path="names/001.json").delete()
        ReferencedPath.objects.get(path="names/002.json").delete()
        ReferencedPath.objects.get(path="names/003.json").delete()
        ReferencedPath.objects.get(path="names/004.json").delete()
        ReferencedPath.objects.get(path="names/005.json").delete()
        call_command("compare_models_and_csv", self.csv_filename)
        self.output = self.output.getvalue()
        self.assertIn("MODEL-ONLY 100/names/0025.json", self.output)
        self.assertIn("MODEL-ONLY 100/names/0035.json", self.output)
        self.assertIn("CSV-ONLY 100/names/001.json", self.output)
        self.assertIn("CSV-ONLY 100/names/002.json", self.output)
        self.assertIn("CSV-ONLY 100/names/003.json", self.output)
        self.assertIn("CSV-ONLY 100/names/004.json", self.output)
        self.assertIn("CSV-ONLY 100/names/005.json", self.output)
        self.assertIn("6 files OK", self.output)
        self.assertIn("2 files in models only", self.output)
        self.assertIn("5 files in CSV only", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_partial_mismatch_no_common_start(self):
        # same as test_partial_mismatch, but without the common beginning
        self.make_file("names/0025.json", self.sl100)
        self.make_file("names/0035.json", self.sl100)
        ReferencedPath.objects.get(path="names/000.json").delete()
        ReferencedPath.objects.get(path="names/001.json").delete()
        ReferencedPath.objects.get(path="names/002.json").delete()
        ReferencedPath.objects.get(path="names/003.json").delete()
        ReferencedPath.objects.get(path="names/004.json").delete()
        call_command("compare_models_and_csv", self.csv_filename)
        self.output = self.output.getvalue()
        self.assertIn("MODEL-ONLY 100/names/0025.json", self.output)
        self.assertIn("MODEL-ONLY 100/names/0035.json", self.output)
        self.assertIn("CSV-ONLY 100/names/000.json", self.output)
        self.assertIn("CSV-ONLY 100/names/001.json", self.output)
        self.assertIn("CSV-ONLY 100/names/002.json", self.output)
        self.assertIn("CSV-ONLY 100/names/003.json", self.output)
        self.assertIn("CSV-ONLY 100/names/004.json", self.output)
        self.assertIn("6 files OK", self.output)
        self.assertIn("2 files in models only", self.output)
        self.assertIn("5 files in CSV only", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_common_finish(self):
        # completely mismatched at first, then come together
        ReferencedPath.objects.get(path="names/000.json").delete()
        ReferencedPath.objects.get(path="names/001.json").delete()
        ReferencedPath.objects.get(path="names/002.json").delete()
        ReferencedPath.objects.get(path="names/003.json").delete()
        self.make_file("names/0025.json", self.sl100)
        self.make_file("names/0035.json", self.sl100)
        call_command("compare_models_and_csv", self.csv_filename)
        self.output = self.output.getvalue()
        self.assertIn("MODEL-ONLY 100/names/0025.json", self.output)
        self.assertIn("MODEL-ONLY 100/names/0035.json", self.output)
        self.assertIn("CSV-ONLY 100/names/000.json", self.output)
        self.assertIn("CSV-ONLY 100/names/001.json", self.output)
        self.assertIn("CSV-ONLY 100/names/002.json", self.output)
        self.assertIn("CSV-ONLY 100/names/003.json", self.output)
        self.assertIn("7 files OK", self.output)
        self.assertIn("2 files in models only", self.output)
        self.assertIn("4 files in CSV only", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_hash_mismatch(self):
        rp003 = ReferencedPath.objects.get(path="names/003.json")
        rp003.awss3etag = "hashhash"
        rp003.save()
        rp005 = ReferencedPath.objects.get(path="names/005.json")
        rp005.awss3etag = ""
        rp005.save()
        rpd = ReferencedPath.objects.get(path="d.json")
        rpd.awss3etag = "not hash"
        rpd.save()
        call_command("compare_models_and_csv", self.csv_filename)
        self.output = self.output.getvalue()
        longstring = "HASH 100/names/003.json hashhash != hashhashhash"
        self.assertIn(longstring, self.output)  # longstr; 79ch line len limit
        self.assertIn("HASH 100/names/005.json  != hashhashhash", self.output)
        self.assertIn("HASH 123/d.json not hash != hashhashhash", self.output)
        self.assertIn("8 files OK", self.output)
        self.assertNotIn("files in models only", self.output)
        self.assertNotIn("files in CSV only", self.output)
        self.assertIn("3 files do not match the hash", self.output)
        self.assertNotIn("Numbers don't add up.", self.output)

    def test_parseline(self):
        line = (
            '"bucket","subpath/filename.extension",'
            '"filesize","hashhashhash","STANDARD",""'
        )
        self.assertEqual(
            parseline(line),
            [
                "bucket",
                "subpath/filename.extension",
                "filesize",
                "hashhashhash",
                "STANDARD",
                "",
            ],
        )

    def test_get_filename(self):
        line = (
            '"bucket","subpath/file/name.extension",'
            '"filesize","hashhashhash","STANDARD",""'
        )
        self.assertEqual(get_filename(line), "file/name.extension")

    def test_get_filename_single_path(self):
        line = (
            '"bucket","subpath/filename.extension",'
            '"filesize","hashhashhash","STANDARD",""'
        )
        self.assertEqual(get_filename(line), "filename.extension")

    def test_get_filename_no_subpath(self):
        line = '"bucket","README.md","filesize","hashhashhash","STANDARD",""'
        self.assertEqual(get_filename(line), "")

    def test_get_subpath(self):
        line = (
            '"bucket","subpath/filename.extension",'
            '"filesize","hashhashhash","STANDARD",""'
        )
        self.assertEqual(get_subpath(line), "subpath")

    def test_get_subpath_no_subpath(self):
        line = '"bucket","README.md","filesize","hashhashhash","STANDARD",""'
        self.assertEqual(get_subpath(line), "README.md")

    def test_get_etag(self):
        line = (
            '"bucket","subpath/filename.extension",'
            '"filesize","hashhashhash","STANDARD",""'
        )
        self.assertEqual(get_etag(line), "hashhashhash")

    def test_map_subpath_locations(self):
        fi = FileIterator(self.csv_filename)
        received = map_subpath_locations(fi)
        expected = {
            "100": {"start": 0, "end": 582, "linecount": 6},
            "123": {"start": 582, "end": 1027, "linecount": 5},
        }
        self.assertEquals(received, expected)
        self.assertEquals(fi.length, 11)

    def test_fileiterator_tell_seek(self):
        fi = FileIterator(self.csv_filename)
        fi.seek(42)
        self.assertEqual(fi.tell(), 42)

    def test_file_iterator_readline(self):
        fi = FileIterator(self.csv_filename)
        line = (
            '"342286153875-genialis-dev-storage",'
            '"100/names/000.json","filesize","hashhashhash","STANDARD",""\n'
        )
        self.assertEqual(fi.readline(), line)
        self.assertEqual(fi.last_position, 0)

    def test_file_iterator_has_next(self):
        fi = FileIterator(self.csv_filename)
        self.assertTrue(fi.has_next())
        fi.seek(fi.size)
        self.assertFalse(fi.has_next())

    def test_file_iterator_next(self):
        fi = FileIterator(self.csv_filename)
        self.assertEquals(fi.next(), ("names/000.json", "hashhashhash"))

    def test_file_iterator_next_at_eof(self):
        fi = FileIterator(self.csv_filename)
        fi.seek(fi.size)
        self.assertEquals(fi.next(), ("", ""))

    def test_file_iterator_restrict(self):
        fi = FileIterator(self.csv_filename)
        fi.restrict(0, 10)
        self.assertTrue(fi.has_next())
        fi.seek(10)
        self.assertFalse(fi.has_next())

    def test_file_iterator_seek_relative(self):
        fi = FileIterator(self.csv_filename)
        fi.restrict(20, 40)
        fi.seek_relative(10)
        self.assertEquals(fi.tell(), 30)

    def test_model_iterator_next(self):
        urls = self.d123.location.files
        urls = urls.exclude(Q(path__endswith="/"))  # exclude directories
        urls = urls.order_by("path")
        URLS = ModelIterator(urls)
        self.assertEquals(URLS.next(), ("d.json", "hashhashhash"))
        self.assertEquals(URLS.next(), ("f.json", "hashhashhash"))
        self.assertEquals(URLS.next(), ("j.json", "hashhashhash"))
        self.assertEquals(URLS.next(), ("k.json", "hashhashhash"))
        self.assertEquals(URLS.next(), ("l.json", "hashhashhash"))
        self.assertEquals(URLS.next(), ("", ""))
        self.assertEquals(URLS.next(), ("", ""))

    def test_model_iterator_has_next(self):
        urls = self.d123.location.files
        urls = urls.exclude(Q(path__endswith="/"))  # exclude directories
        urls = urls.order_by("path")
        URLS = ModelIterator(urls)
        self.assertTrue(URLS.has_next())
        URLS.next()  # 123/d.json
        self.assertTrue(URLS.has_next())
        URLS.next()  # 123/f.json
        self.assertTrue(URLS.has_next())
        URLS.next()  # 123/j.json
        self.assertTrue(URLS.has_next())
        URLS.next()  # 123/k.json
        self.assertTrue(URLS.has_next())
        URLS.next()  # 123/l.json
        self.assertFalse(URLS.has_next())
