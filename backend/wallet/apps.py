from django.apps import AppConfig


class WalletConfig(AppConfig):
    name = 'wallet'

    def ready(self):
        from . import signals  # noqa: F401 — registers the post_save receiver
