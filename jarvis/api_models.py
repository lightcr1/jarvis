from pydantic import BaseModel, Field


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


class AdminSettingsIn(BaseModel):
    usage_limits: AdminUsageLimitsIn = Field(default_factory=AdminUsageLimitsIn)
    voice: AdminVoiceSettingsIn = Field(default_factory=AdminVoiceSettingsIn)
    home_assistant: AdminHomeAssistantSettingsIn = Field(default_factory=AdminHomeAssistantSettingsIn)


class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=1)
    enabled: bool = True
    metric: str = Field(default="cpu", pattern="^(cpu|ram|disk|ha_entity)$")
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
