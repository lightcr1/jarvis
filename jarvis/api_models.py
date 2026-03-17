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


class UserPreferencesIn(BaseModel):
    display_name: str = ""
    accent_color: str = "cyan"
    auto_play_voice: bool = True
    compact_mode: bool = False
    orb_detail: str = "high"
    theme: str = "dark"


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


class AdminSettingsIn(BaseModel):
    usage_limits: AdminUsageLimitsIn = Field(default_factory=AdminUsageLimitsIn)
    voice: AdminVoiceSettingsIn = Field(default_factory=AdminVoiceSettingsIn)
