from PySide6.QtCore import QCoreApplication

from ground_station.single_instance import acquire


def test_a_second_copy_is_refused_until_the_first_lets_go(tmp_path):
    QCoreApplication.instance() or QCoreApplication([])
    path = tmp_path / "app.lock"
    first = acquire(path)
    assert first is not None
    assert acquire(path) is None
    first.unlock()
    again = acquire(path)
    assert again is not None
    again.unlock()
