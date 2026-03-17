# Deploy Validation

- Date:
- Operator:
- Host / VM:
- Environment:

## Preconditions

- Clean host or clean snapshot used:
- Config source:
- TLS mode:

## Commands

```bash
sudo cp config/env/prod.env.example /etc/jarvis/config.env
sudo ./scripts/deploy_local.sh
curl -k https://localhost/health || curl -k https://localhost:443/health
systemctl status jarvis.service
```

## Results

- Deploy command result:
- Health check result:
- Service status result:
- UI reachable:

## Notes

- 
