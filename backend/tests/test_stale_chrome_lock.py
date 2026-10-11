"""setup_driver()'s stale-lock cleanup: a crashed/zombie Chrome from a prior
run leaves SingletonLock/-Cookie/-Socket (and sometimes a live process)
pinned to the profile dir, which makes the next launch fail with "session
not created: Chrome instance exited". _kill_stale_chrome() clears that."""
import os

from app.integrations.dedge.bar_updater import _kill_stale_chrome


def test_clears_singleton_lock_files(tmp_path):
    profile_dir = str(tmp_path)
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        open(os.path.join(profile_dir, name), "w").close()

    _kill_stale_chrome(profile_dir)

    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        assert not os.path.exists(os.path.join(profile_dir, name))


def test_no_error_when_nothing_to_clean(tmp_path):
    # Must not raise even when the profile dir has none of the lock files.
    _kill_stale_chrome(str(tmp_path))
