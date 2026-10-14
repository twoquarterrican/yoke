from yoke_harness.session_relay_schedule import relay_run_lock


def test_relay_run_lock_excludes_and_releases(tmp_path):
    with relay_run_lock(tmp_path) as first:
        assert first
        with relay_run_lock(tmp_path) as second:
            assert not second

    with relay_run_lock(tmp_path) as after_release:
        assert after_release
