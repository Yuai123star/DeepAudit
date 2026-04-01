"""
Tests for Pydantic schemas: token, user, audit_rule, prompt_template.
"""

import pytest
from pydantic import ValidationError

from app.schemas.token import Token, TokenPayload
from app.schemas.user import UserCreate, UserUpdate, User, UserListResponse
from app.schemas.audit_rule import (
    AuditRuleCreate,
    AuditRuleSetCreate,
    AuditRuleSetBase,
)
from app.schemas.prompt_template import (
    PromptTemplateCreate,
    PromptTemplateUpdate,
    PromptTestRequest,
)


# ==================== Token Schemas ====================


class TestToken:
    def test_token_creation(self):
        token = Token(access_token="abc123", token_type="bearer")
        assert token.access_token == "abc123"
        assert token.token_type == "bearer"

    def test_token_payload_with_sub(self):
        payload = TokenPayload(sub="user123")
        assert payload.sub == "user123"

    def test_token_payload_optional_sub(self):
        payload = TokenPayload()
        assert payload.sub is None


# ==================== User Schemas ====================


class TestUserCreate:
    def test_user_create_valid(self):
        user = UserCreate(
            email="test@example.com",
            password="secure_password",
            full_name="Test User",
        )
        assert user.email == "test@example.com"
        assert user.password == "secure_password"
        assert user.full_name == "Test User"
        assert user.is_active is True
        assert user.is_superuser is False
        assert user.role == "member"

    def test_user_create_invalid_email(self):
        with pytest.raises(ValidationError):
            UserCreate(
                email="not-an-email",
                password="secure_password",
                full_name="Test User",
            )

    def test_user_create_missing_password(self):
        with pytest.raises(ValidationError):
            UserCreate(
                email="test@example.com",
                full_name="Test User",
            )


class TestUserUpdate:
    def test_user_update_all_optional(self):
        update = UserUpdate()
        assert update.email is None
        assert update.password is None
        assert update.full_name is None
        assert update.phone is None


class TestUserListResponse:
    def test_user_list_response(self):
        user_data = {
            "id": "user-1",
            "email": "test@example.com",
            "full_name": "Test User",
            "created_at": None,
            "updated_at": None,
        }
        user = User(**user_data)
        response = UserListResponse(
            users=[user],
            total=1,
            skip=0,
            limit=10,
        )
        assert response.total == 1
        assert len(response.users) == 1
        assert response.users[0].id == "user-1"


# ==================== AuditRule Schemas ====================


class TestAuditRuleCreate:
    def test_audit_rule_create_minimal(self):
        rule = AuditRuleCreate(
            rule_code="SQL-001",
            name="SQL Injection Detection",
            category="security",
        )
        assert rule.rule_code == "SQL-001"
        assert rule.name == "SQL Injection Detection"
        assert rule.category == "security"
        assert rule.severity == "medium"
        assert rule.enabled is True

    def test_audit_rule_create_name_too_long(self):
        with pytest.raises(ValidationError):
            AuditRuleCreate(
                rule_code="SQL-001",
                name="x" * 201,
                category="security",
            )

    def test_audit_rule_create_rule_code_empty(self):
        with pytest.raises(ValidationError):
            AuditRuleCreate(
                rule_code="",
                name="SQL Injection Detection",
                category="security",
            )


class TestAuditRuleSetCreate:
    def test_audit_rule_set_create_default_weights(self):
        rule_set = AuditRuleSetCreate(name="Default Rule Set")
        assert rule_set.name == "Default Rule Set"
        assert rule_set.severity_weights == {
            "critical": 10,
            "high": 5,
            "medium": 2,
            "low": 1,
        }

    def test_audit_rule_set_create_with_rules(self):
        rules = [
            AuditRuleCreate(
                rule_code="SQL-001",
                name="SQL Injection",
                category="security",
            ),
            AuditRuleCreate(
                rule_code="XSS-001",
                name="Cross-Site Scripting",
                category="security",
            ),
        ]
        rule_set = AuditRuleSetCreate(
            name="Security Rules",
            rules=rules,
        )
        assert rule_set.name == "Security Rules"
        assert len(rule_set.rules) == 2
        assert rule_set.rules[0].rule_code == "SQL-001"
        assert rule_set.rules[1].rule_code == "XSS-001"


# ==================== PromptTemplate Schemas ====================


class TestPromptTemplateCreate:
    def test_prompt_template_create_valid(self):
        template = PromptTemplateCreate(
            name="SQL Injection Detector",
            content_zh="\u68c0\u6d4bSQL\u6ce8\u5165",
            content_en="Detect SQL injection",
        )
        assert template.name == "SQL Injection Detector"
        assert template.template_type == "system"
        assert template.is_active is True

    def test_prompt_template_create_name_too_long(self):
        with pytest.raises(ValidationError):
            PromptTemplateCreate(name="x" * 101)


class TestPromptTemplateUpdate:
    def test_prompt_template_update_all_optional(self):
        update = PromptTemplateUpdate()
        assert update.name is None
        assert update.description is None
        assert update.content_zh is None
        assert update.is_active is None


class TestPromptTestRequest:
    def test_prompt_test_request_required_fields(self):
        req = PromptTestRequest(
            content="Analyze this code",
            code="print('hello')",
        )
        assert req.content == "Analyze this code"
        assert req.code == "print('hello')"

    def test_prompt_test_request_defaults(self):
        req = PromptTestRequest(
            content="Analyze this code",
            code="print('hello')",
        )
        assert req.language == "python"
        assert req.output_language == "zh"

    def test_prompt_test_request_missing_content(self):
        with pytest.raises(ValidationError):
            PromptTestRequest(code="print('hello')")

    def test_prompt_test_request_missing_code(self):
        with pytest.raises(ValidationError):
            PromptTestRequest(content="Analyze this code")
