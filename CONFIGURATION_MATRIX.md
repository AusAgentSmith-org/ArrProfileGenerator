# ProfSync Configuration Matrix

High-level mapping of wizard answers → applied configuration values.

## User Profile Answers → Internal Flags

| Answer | Internal Field | Possible Values | Notes |
|--------|---|---|---|
| Target resolution | `resolution` | `hd`, `uhd`, `both` | Determines which quality tiers are enabled |
| Media consumption | `consumption` | `home`, `remote` | `remote` enables transcode options |
| Can server transcode | `can_transcode` | `True`, `False` | Only asked if `consumption == "remote"` |
| Device capability | `device_capability` | `legacy`, `mixed`, `modern` | Determines HEVC/x265 support |
| HDR support | `hdr_support` | `none`, `hdr10`, `full` | Only asked if `resolution in ("uhd", "both")` |
| Audio preference | `audio_preference` | `standard`, `lossless` | Affects custom format scoring |
| Include remux | `include_remux` | `True`, `False` | Very large files (30-80GB) |
| Storage constraints | `storage_constraint` | `none`, `moderate`, `tight` | Affects Bluray inclusion |
| Strictness | `strictness` | `strict`, `balanced`, `permissive` | Affects release group scoring |
| Auto-upgrade | `auto_upgrade` | `True`, `False` | Whether to grab better releases |

---

## Derived Flags (Calculated from Answers)

| Derived Flag | Calculation | Effect |
|---|---|---|
| `wants_hevc` | `device_capability in ("modern", "mixed")` | Adds +100 score to HEVC/x265 custom format |
| `wants_hdr` | `hdr_support in ("full", "hdr10")` | Adds HDR10 and optionally Dolby Vision CFs |

---

## Quality Profile Configuration

### Quality Tiers Enabled (by Resolution)

#### 4K UHD (`resolution == "uhd"`)
| Quality | Included? | Notes |
|---------|---|---|
| Remux-2160p | If `include_remux` AND `storage != tight` | Lossless video |
| Bluray-2160p | ✓ Always | Best UHD quality |
| WEBDL-2160p | ✓ Always | UHD streaming rips |
| WEBRip-2160p | ✓ Always | UHD P2P rips |
| Remux-1080p | ✗ Never | Lower than cutoff for 4K |
| All 1080p others | ✗ Never | Lower than cutoff for 4K |

**Cutoff Quality** (where search stops): Remux-2160p > Bluray-2160p > WEBDL-2160p > WEBRip-2160p

#### 1080p HD (`resolution == "hd"`)
| Quality | Included? | Notes |
|---------|---|---|
| Remux-1080p | If `include_remux` AND `storage != tight` | Lossless video |
| Bluray-1080p | If `storage != tight` | Best HD quality |
| WEBDL-1080p | ✓ Always | HD streaming rips |
| WEBRip-1080p | ✓ Always | HD P2P rips |
| Any 2160p | ✗ Never | Above HD selection |

**Cutoff Quality** (where search stops): Remux-1080p > Bluray-1080p > WEBDL-1080p > WEBRip-1080p

**If `storage == "tight"`**: Bluray removed, only WEB qualities remain

#### Both (`resolution == "both"`)
| Quality | Included? | Priority |
|---------|---|---|
| Remux-2160p | If `include_remux` AND `storage != tight` | 1st (highest) |
| Bluray-2160p | If `storage != tight` | 2nd |
| WEBDL-2160p, WEBRip-2160p | ✓ Always | 3rd |
| Remux-1080p | If `include_remux` AND `storage != tight` | 4th |
| Bluray-1080p | If `storage != tight` | 5th |
| WEBDL-1080p, WEBRip-1080p | ✓ Always | 6th |

**Cutoff Quality**: Prefers highest UHD available, falls back to HD

### Permanently Excluded Qualities
These are **ALWAYS disabled** regardless of settings:
- RAW-HD
- Unknown
- TELECINE
- TELESYNC
- CAM
- WORKPRINT

---

## Release Group Quality Scoring

Scores vary by **strictness** level. Higher scores = preferred, negative = penalized.

### Tier Scores by Strictness

| Tier | Strict | Balanced | Permissive |
|------|--------|----------|-----------|
| Tier 01 (A+/A) | +1500 | +1500 | +1500 |
| Tier 02 (B+/B) | -2000 | +400 | +200 |
| Tier 03 (C+/C) | -4000 | -100 | +50 |
| LQ (F) | -10000 | -10000 | -10000 |

### Format Score Thresholds

Determines which releases are grabbed and when to stop upgrading.

| Setting | Strict | Balanced | Permissive |
|---------|--------|----------|-----------|
| **Min Format Score** | 399 | -9999 | -9999 |
| **Cutoff Format Score** | 999 | 1499 | 1499 |
| **Min Upgrade Score** | 399 | 1 | 1 |

**Interpretation:**
- **Min Format Score**: Don't grab anything below this score
- **Cutoff Format Score**: Stop upgrading once you reach this score
- **Min Upgrade Score**: API requirement (must be ≥ 1)

---

## Custom Formats Applied

### Release Group CFs
| strictness | Tiers Included |
|---|---|
| `strict` | Tier 01 only (penalizes Tier 02+) |
| `balanced` | Tier 01, 02, and 03 |
| `permissive` | All tiers (but still penalizes LQ) |

### Codec CFs (Conditional)

| Condition | Custom Format | Score |
|---|---|---|
| `device_capability == "legacy"` | ProfSync x264 Preferred | +200 |
| `device_capability == "legacy"` | ProfSync x265 Penalty | -500 |
| `device_capability in ("modern", "mixed")` | ProfSync HEVC/x265 | +100 |

### Audio CFs (Conditional)

| Condition | Custom Format | Score |
|---|---|---|
| `audio_preference == "lossless"` | ProfSync Lossless Audio | +200 |

Matches: TrueHD, DTS-HD, DTS-MA, LPCM, FLAC, Atmos

### HDR CFs (Conditional)

| Condition | Custom Format | Score |
|---|---|---|
| `hdr_support in ("full", "hdr10")` | ProfSync HDR10 | +100 |
| `hdr_support == "full"` | ProfSync Dolby Vision | +150 |

---

## Example Profiles

### Example 1: 4K Enthusiast
```
Resolution: 4K UHD only
Consumption: Home
Device: Modern (Apple TV 4K, etc)
HDR: Full (HDR10 + Dolby Vision)
Audio: Lossless
Remux: Yes
Storage: None (unlimited)
Strictness: Balanced
Auto-upgrade: Yes
```

**Result:**
- ✓ Enabled: Remux-2160p, Bluray-2160p, WEBDL-2160p, WEBRip-2160p
- 🎯 Cutoff: Remux-2160p
- 📊 Release Group Scores: Tier 01 (+1500), Tier 02 (+400), Tier 03 (-100), LQ (-10000)
- 🎨 Custom Formats: HEVC/x265 (+100), Lossless Audio (+200), HDR10 (+100), Dolby Vision (+150)
- ⬆️ Min Format Score: -9999 (grab almost anything), Cutoff: 1499 (stop upgrading at this score)

### Example 2: Storage-Conscious 1080p
```
Resolution: 1080p HD only
Consumption: Remote streaming
Can Transcode: Yes
Device: Mixed (some old devices)
Audio: Standard
Remux: No
Storage: Tight
Strictness: Permissive
Auto-upgrade: No
```

**Result:**
- ✓ Enabled: WEBDL-1080p, WEBRip-1080p (Bluray/Remux excluded)
- 🎯 Cutoff: WEBRip-1080p (highest available after exclusions)
- 📊 Release Group Scores: Tier 01 (+1500), Tier 02 (+200), Tier 03 (+50), LQ (-10000)
- 🎨 Custom Formats: None (legacy device handling not triggered, no lossless)
- ⬆️ Min Format Score: -9999, Cutoff: 1499, Auto-upgrade disabled

### Example 3: Balanced 4K with Both Fallback
```
Resolution: Both (4K preferred, 1080p fallback)
Consumption: Home
Device: Modern
HDR: HDR10 only
Audio: Lossless
Remux: Yes
Storage: Moderate
Strictness: Strict
Auto-upgrade: Yes
```

**Result:**
- ✓ Enabled: Remux-2160p, Bluray-2160p, WEBDL-2160p, WEBRip-2160p, WEBDL-1080p, WEBRip-1080p (no Bluray-1080p due to moderate storage)
- 🎯 Cutoff: Remux-2160p (prefers 4K first)
- 📊 Release Group Scores: Tier 01 only (+1500), everything else penalized
- 🎨 Custom Formats: HEVC/x265 (+100), Lossless Audio (+200), HDR10 (+100)
- ⬆️ Min Format Score: 399 (strict minimum), Cutoff: 999 (stop upgrading early)

---

## Quick Reference: Answer → Score Impact

| Answer | Positive Impact | Negative Impact |
|--------|---|---|
| Modern devices | +HEVC/x265 bonus | None |
| Legacy devices | +x264 bonus | -x265 penalty |
| Full HDR support | +HDR10, +Dolby Vision | None |
| Lossless audio | +Lossless Audio | None |
| Include Remux | Adds best-quality option | Very large files |
| Strict mode | Highest quality guarantee | Fewer groups available |
| Permissive mode | More groups available | Lower average quality |
| Tight storage | Smaller files | Only WEB qualities |

