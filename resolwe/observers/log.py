import logging
from django.db.models import Count

logger = logging.getLogger(__name__)


def log(*args, **kwargs):
    logger.warning(
        " ".join([str(arg) for arg in args])
        + "".join(["\n  " + str(key) + " = " + str(val) for key, val in kwargs.items()])
    )


def status(Observer, Subscription):
    obs = "Observers:\n" + "\n".join(
        [
            f"({o.pk}) {o.content_type} {o.object_id} {o.change_type} subs={o.subs}"
            for o in Observer.objects.annotate(subs=Count("subscriptions")).all()
        ]
    )

    subs = ""
    for sub in Subscription.objects.all():
        subs += f"\nSubscription ({sub.pk}) = {sub.subscription_id} of {sub.user}"
        for ob in sub.observers.all():
            subs += f"\n  + {ob.pk}"

    return "\n" + obs + "\n" + subs
