"""The approved capture bound must agree in storage, config and every comparator."""

from copy import deepcopy

import pytest

from pipelines.ingestion.bronze import CAPTURE_MAX_BYTES
from projectctl.config import InputError, load_config, load_yaml, validate_config


def test_all_variants_use_the_approved_two_mib_capture_cap():
    config = load_config()
    assert CAPTURE_MAX_BYTES == 2 * 1024 * 1024
    for variant in config.variants.values():
        assert variant.config.raw_capture_max_bytes == CAPTURE_MAX_BYTES
        assert variant.config.raw_capture_max_wait_ms == 50


@pytest.mark.parametrize("variant", ["B0", "O1"])
def test_stale_one_mib_capture_cap_is_rejected(variant):
    data = deepcopy(load_yaml("configs/evaluation.yaml"))
    data["variants"][variant]["config"]["raw_capture_max_bytes"] = 1024 * 1024
    with pytest.raises(InputError):
        validate_config(data)
