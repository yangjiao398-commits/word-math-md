from word_math_md.legal_terms import LEGAL_VERSION, validate_registration_consent


def test_consent_requires_terms_and_age():
    try:
        validate_registration_consent(
            age_group="adult",
            accept_minor_terms=False,
            accept_ip_terms=True,
            guardian_consent=False,
            terms_version=LEGAL_VERSION,
        )
        assert False, "should reject"
    except ValueError as exc:
        assert "未成年人保护" in str(exc)


def test_minor_requires_guardian():
    try:
        validate_registration_consent(
            age_group="teen",
            accept_minor_terms=True,
            accept_ip_terms=True,
            guardian_consent=False,
            terms_version=LEGAL_VERSION,
        )
        assert False, "should reject"
    except ValueError as exc:
        assert "监护人" in str(exc)


def test_adult_consent_ok():
    data = validate_registration_consent(
        age_group="adult",
        accept_minor_terms=True,
        accept_ip_terms=True,
        guardian_consent=False,
        terms_version=LEGAL_VERSION,
    )
    assert data["age_group"] == "adult"
    assert data["version"] == LEGAL_VERSION


def test_child_with_guardian_ok():
    data = validate_registration_consent(
        age_group="child",
        accept_minor_terms=True,
        accept_ip_terms=True,
        guardian_consent=True,
        terms_version=LEGAL_VERSION,
    )
    assert data["guardian"] is True


def test_runtime_config_includes_legal():
    from word_math_md.app_api import app_runtime_config

    cfg = app_runtime_config()
    assert cfg["legal"]["version"] == LEGAL_VERSION
    titles = [d["title"] for d in cfg["legal"]["documents"]]
    assert any("未成年人" in t for t in titles)
    assert any("知识产权" in t for t in titles)
