"""临时探针：验证 CI 红灯与 needs 门禁（本提交随后 revert，勿保留）。"""


def test_ci_gate_probe() -> None:
    assert False, "CI gate probe: intentional failure"
