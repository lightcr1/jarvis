import re as _re

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ChatIn(BaseModel):
    text: str
    session_id: str | None = None
    source: str | None = None


class ChatOut(BaseModel):
    reply: str
    data: dict | None = None
    session_id: str | None = None


class ChatSessionCreateIn(BaseModel):
    title: str | None = None


class ChatSessionUpdateIn(BaseModel):
    title: str


class ChatMessage(BaseModel):
    role: str
    text: str
    ts: int


class ChatSessionOut(BaseModel):
    id: str
    title: str
    updated_at: int
    created_at: int
    messages: list[ChatMessage] = Field(default_factory=list)


class UnlockIn(BaseModel):
    passphrase: str


class TTSIn(BaseModel):
    text: str
    voice: str = ""


class UnlockOut(BaseModel):
    token: str
    expires_in_sec: int


class AdminLoginIn(BaseModel):
    username: str
    password: str


class AdminLoginOut(UnlockOut):
    user_id: str
    username: str
    role: str


class UserLoginIn(BaseModel):
    username: str
    password: str


class UserPasswordIn(BaseModel):
    password: str = Field(min_length=1)


class UserChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=6)


class UserPreferencesIn(BaseModel):
    display_name: str = ""
    accent_color: str = "cyan"
    auto_play_voice: bool = True
    compact_mode: bool = False
    orb_detail: str = "high"
    theme: str = "dark"
    location: str = ""
    notes: list[str] = []
    tts_voice: str = ""
    morning_briefing_enabled: bool = False
    morning_briefing_time: str = "07:30"
    quick_actions: list[str] = []
    notifications_enabled: bool = True
    persona_tone: str = "formal"


class AdminUserCreateIn(BaseModel):
    username: str
    role: str = "standard_user"
    enabled: bool = True
    password: str | None = None


class AdminUserUpdateIn(BaseModel):
    role: str | None = None
    enabled: bool | None = None


class AdminGroupCreateIn(BaseModel):
    name: str
    description: str = ""


class AdminGroupUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None


class AdminMembershipIn(BaseModel):
    user_id: str
    group_id: str


class AdminPermissionSetIn(BaseModel):
    permissions: list[str] = Field(default_factory=list)


class AdminUsageLimitsIn(BaseModel):
    token_ttl_min: int = Field(default=20, ge=1)
    max_active_tokens: int = Field(default=200, ge=1)


class AdminVoiceSettingsIn(BaseModel):
    wakeword_enabled: bool = False
    wakeword_phrase: str = Field(default="hey jarvis", min_length=1)
    stt_provider: str = Field(default="local", pattern="^(local|gemini)$")


class AdminHomeAssistantSettingsIn(BaseModel):
    confirmation_ttl_sec: int = Field(default=300, ge=30)
    remote_allowed_cidrs: list[str] = Field(default_factory=list)


class AdminModelPriceIn(BaseModel):
    in_price: float = Field(default=0.0, ge=0, alias="in")
    out_price: float = Field(default=0.0, ge=0, alias="out")
    tier: str = Field(default="medium")
    expensive: bool = False

    model_config = {"populate_by_name": True}


class AdminProviderSettingsIn(BaseModel):
    default_provider: str = "openrouter"
    openrouter_enabled: bool = True
    usd_to_chf_rate: float = Field(default=0.90, gt=0)
    model_prices: dict[str, AdminModelPriceIn] = Field(default_factory=dict)
    global_daily_budget_chf: float = Field(default=0.0, ge=0)
    global_monthly_budget_chf: float = Field(default=0.0, ge=0)
    kill_switch: bool = False
    disable_expensive_models: bool = False
    expensive_threshold_chf: float = Field(default=0.10, ge=0)


class AdminSettingsIn(BaseModel):
    usage_limits: AdminUsageLimitsIn = Field(default_factory=AdminUsageLimitsIn)
    voice: AdminVoiceSettingsIn = Field(default_factory=AdminVoiceSettingsIn)
    home_assistant: AdminHomeAssistantSettingsIn = Field(default_factory=AdminHomeAssistantSettingsIn)
    provider: AdminProviderSettingsIn = Field(default_factory=AdminProviderSettingsIn)


class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=1)
    enabled: bool = True
    metric: str = Field(default="cpu", pattern="^(cpu|ram|disk|ha_health|ha_entity)$")
    condition: str = Field(default="above", pattern="^(above|below|equals|contains)$")
    threshold: float | str = 80.0
    duration_seconds: int = Field(default=0, ge=0)
    severity: str = Field(default="warning", pattern="^(info|warning|critical)$")
    cooldown_seconds: int = Field(default=300, ge=60)
    ha_entity_id: str | None = None
    ha_attribute: str | None = None
    message_template: str = "Alert: {metric} is {value} (threshold: {threshold})"


class AlertRuleUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    metric: str | None = None
    condition: str | None = None
    threshold: float | str | None = None
    duration_seconds: int | None = None
    severity: str | None = None
    cooldown_seconds: int | None = None
    ha_entity_id: str | None = None
    ha_attribute: str | None = None
    message_template: str | None = None


class HomeAssistantDiscoveryCandidateIn(BaseModel):
    source: str = Field(default="manual")
    ip_address: str = Field(min_length=1)
    label: str = Field(min_length=1)
    suggested_type: str = Field(min_length=1)
    suggested_area: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


class MemoryNoteCreate(BaseModel):
    text: str


class MemoryNoteResponse(BaseModel):
    id: str
    text: str
    created_at: int


class MemoryAliasCreate(BaseModel):
    alias: str
    target: str


class MemoryAliasResponse(BaseModel):
    alias: str
    target: str
    created_at: int


class MemorySummaryResponse(BaseModel):
    notes: list[MemoryNoteResponse] = Field(default_factory=list)
    aliases: list[MemoryAliasResponse] = Field(default_factory=list)
    note_count: int = 0
    alias_count: int = 0



class ByokKeyIn(BaseModel):
    api_key: str = Field(min_length=8)


class ByokKeyOut(BaseModel):
    provider: str
    masked: str
    label: str | None = None
    created_at: int


class TopUpIn(BaseModel):
    user_id: str = Field(min_length=1)
    amount_chf: float = Field(gt=0)
    note: str = ""


class UserLimitsIn(BaseModel):
    chf_per_day: float | None = Field(default=None, ge=0)
    chf_per_month: float | None = Field(default=None, ge=0)
    tokens_per_request: int | None = Field(default=None, ge=0)
    requests_per_min: int | None = Field(default=None, ge=1, le=300)
    expensive_models_per_day: int | None = Field(default=None, ge=0)
    allowed_models: list[str] | None = None


class SignupIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=6)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError("invalid email address")
        return v.strip().lower()

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("username cannot be blank")
        return cleaned


class SignupVerifyIn(BaseModel):
    email: str
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class SignupResendIn(BaseModel):
    email: str


class SignupConfigOut(BaseModel):
    enabled: bool
