# Harness

GPU connection skills for reproducibility agents.

## Contents

- `gpu_skills.py` — SSH-based GPU execution for reproducibility agents (`04_reproducibility_and_transparency.md`)
- `scaffolding.md` — legacy scaffolding prompt (GPU tools are now embedded directly in the reproducibility role)

## GPU backends

| Class | Server | Notes |
|-------|--------|-------|
| `ServerlessGPUSkill` | FPT Cloud (2x H100 80GB) | `ssh root@tcp-endpoint.serverless.fptcloud.com -p 34919 -i ~/.ssh/id_rsa` |
| `GPUSandboxSkill` | McGill AWS (8x RTX A6000) | `ssh -p 2222 kushasareen@ec2-35-182-158-243.ca-central-1.compute.amazonaws.com -i ~/.ssh/id_rsa` |

Each agent writes to `/data/<agent_id>/` on the sandbox to avoid collisions.

GPU access instructions are included only in `agent_definition/roles/04_reproducibility_and_transparency.md` — other roles do not receive them.
