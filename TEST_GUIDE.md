# ProfSync Test Stack Guide

Complete walkthrough for testing the ProfSync wizard with a local Sonarr/Radarr stack.

## 1. Start the Test Stack

```bash
cd test
./init-stack.sh
```

This will:
- Start Sonarr (port 8989) and Radarr (port 7878)
- Wait for both services to initialize
- Extract API keys from their config files
- Write credentials to `.env`
- Configure root folders

**Output example:**
```
=== Test Stack Ready ===

Sonarr:
  URL: http://localhost:8989
  Web: http://localhost:8989
  API Key: abc123def456...

Radarr:
  URL: http://localhost:7878
  Web: http://localhost:7878
  API Key: xyz789uvw012...

Run the wizard with:
  python ../wizard.py --teststack
```

## 2. Run the Wizard in Teststack Mode

```bash
cd ..
python wizard.py --teststack
```

The wizard will:
1. ✓ Auto-load Sonarr and Radarr credentials from `test/.env`
2. Ask 12 questions about your preferences
3. Fetch TRaSH Guides tier data from GitHub
4. Create custom formats and quality profiles
5. Apply to both Sonarr and Radarr
6. Offer to bulk-update existing series/movies

**Example run:**
```
╔══════════════════════════════════════════════════════════╗
║               ProfSync Configuration Wizard              ║
║                                                          ║
║  Sonarr/Radarr setup from TRaSH Guides data              ║
╚══════════════════════════════════════════════════════════╝

✓ Loaded Sonarr from teststack (http://localhost:8989)
✓ Loaded Radarr from teststack (http://localhost:7878)

Fetching TRaSH tier data... done (100+ groups across 4 tiers)

Built 18 custom formats

Configuring Sonarr (http://localhost:8989)...
  Connected to Sonarr v4.0.x
  Triggering backup...
  ...
```

## 3. Verify in Web UIs

Open in browser:
- **Sonarr**: http://localhost:8989
  - Go to Settings > Custom Formats → see "ProfSync Tier 01/02/03/LQ"
  - Go to Settings > Profiles → see "ProfSync HD" or "ProfSync UHD"

- **Radarr**: http://localhost:7878
  - Go to Settings > Custom Formats → see "ProfSync Tier 01/02/03/LQ"
  - Go to Settings > Profiles → see "ProfSync HD" or "ProfSync UHD"

## 4. Interactive Mode (Optional)

If you want to test manual configuration:

```bash
python wizard.py
```

Then enter:
- **Sonarr URL**: `http://localhost:8989`
- **Sonarr API Key**: (from `test/.env`)
- **Radarr URL**: `http://localhost:7878`
- **Radarr API Key**: (from `test/.env`)

## 5. Cleanup

When done testing:

```bash
cd test
./cleanup-stack.sh
```

Choose whether to keep or remove data volumes.

## Troubleshooting

**Services won't start:**
```bash
# Check logs
docker-compose logs sonarr
docker-compose logs radarr

# Rebuild containers
docker-compose down
docker-compose up -d
```

**API key extraction fails:**
- Wait a bit longer (services can take 30+ seconds to initialize)
- Manually check: `cat sonarr-config/config.xml | grep ApiKey`

**Port conflicts:**
- Stop other services on ports 8989/7878
- Edit `docker-compose.yml` to use different ports
- Update `test/.env` URLs accordingly

**Wizard can't find test stack:**
- Ensure `test/.env` exists (created by `init-stack.sh`)
- Check it has `SONARR_URL`, `SONARR_API_KEY`, etc.
- Make sure you're running wizard from the root profsync directory

## Workflow for Development

1. **Setup**: `cd test && ./init-stack.sh && cd ..`
2. **Modify code** in `src/main.py`, `src/profile_builder.py`, etc.
3. **Test**: `python wizard.py --teststack`
4. **Verify**: Check Sonarr/Radarr web UIs
5. **Repeat**: Go back to step 2
6. **Cleanup**: `cd test && ./cleanup-stack.sh`

This allows rapid iteration without waiting for full initialization each time.
