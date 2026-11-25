import pytest
from django.core.exceptions import ValidationError

from catalog.models import normalize_countries


def test_countries_normalized_and_validated():
    assert normalize_countries(["jp", "KR", "jp", " sg "]) == ["JP", "KR", "SG"]
    for bad in ([], ["xx"], ["JPN"], [""]):
        with pytest.raises(ValidationError):
            normalize_countries(bad)
