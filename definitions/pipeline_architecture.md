# Pipeline Architecture

## Overview

This document defines the execution flow, responsibilities, and data transformations of the EVPN/VXLAN configuration pipeline.
The pipeline converts human-authored intent (`fabric.yaml`) into fully rendered, deterministic per-device configurations.

The system is designed to be:
- deterministic
- validated at every stage
- scalable for day-1 and day-2 operations

---

## Project Structure

```text
evpn/
├── initial_prompt.txt
│   ├── definitions/
│   ├── conventions.md
│   ├── network_architecture.md
│   └── pipeline_architecture.md
│   ├── intent/
│   └── fabric.yaml
│   ├── pipeline/
│   ├── validate_fabric_yaml.py
│   ├── build_model.py
│   ├── validate_model.py
│   ├── render_configs.py
│   └── main.py
│   ├── outputs/
│   └── notes/
└── commit.txt
```

---

## Execution Flow

```text
Human
│
▼
intent/fabric.yaml
│
▼
pipeline/validate_fabric_yaml.py
│   ├── FAIL → STOP (show errors)
│   └── PASS
▼
pipeline/build_model.py
▼
derived model
▼
pipeline/validate_model.py
│   ├── FAIL → STOP (show errors)
│   └── PASS
▼
pipeline/render_configs.py
▼
device configurations
```

---

## Data Movement

```text
definitions/network_architecture.md ─┐
                                     ├── defines rules and semantics
definitions/conventions.md ---------┘
                │
                ▼
intent/fabric.yaml
                ▼
pipeline/validate_fabric_yaml.py
                ▼
          validated intent
                ▼
pipeline/build_model.py
  ├── uses definitions/conventions.md
  ├── uses definitions/network_architecture.md
                ▼
            derived model
                ▼
pipeline/validate_model.py
                ▼
           validated model
                ▼
pipeline/render_configs.py
                ▼
            configurations
```

---

## Pipeline Stages

### 1. Intent (Input)

**Source:** `intent/fabric.yaml`

**Purpose:**
- Define desired state of the network

**Rules:**
- Human-authored only
- Declarative only (no derived values)
- Must follow:
  - `definitions/network_architecture.md`
  - `definitions/conventions.md`

**Intent Boundaries:**
- `fabric.yaml` is the single source of truth for deployment intent.
- It defines what should exist in the fabric, not how devices should be configured.
- It may define fabrics, blocks, tenants, VRFs, VLANs, placement, and optional static routes.
- It must not define derived values such as VNI, RD, RT, loopbacks, P2P addressing, router IDs, protocol neighbor relationships, or rendered device-level configuration.

---

### 2. Intent Validation

**Module:** `pipeline/validate_fabric_yaml.py`

**Purpose:**
- Validate correctness of input before processing

**Validates:**
- structure (fabrics, tenants, VLANs, attachment)
- references (fabric_id, block, leaf_pair)
- ranges (VLAN IDs, VRF IDs)
- semantics (for example multisite VLAN usage)
- consistency (no duplicates, all VLANs attached)

**Validation Contract:**
- required top-level sections must be present
- references must be valid
- required identifiers must be unique
- forbidden or derived-only fields must not appear in intent
- validated intent remains declarative input and is not enriched with derived values at this stage

**Output:**
- PASS → continue
- FAIL → stop pipeline

---

### 3. Model Build

**Module:** `pipeline/build_model.py`

**Purpose:**
- Convert intent into full derived model

**Responsibilities:**
- parse intent
- normalize intent
- expand topology (devices, leaf pairs)
- compute derived values:
  - VLAN classification
  - VNI (L2/L3)
  - RD / RT
  - loopbacks
  - P2P addressing
  - router IDs
  - BGP/EVPN relationships

**Derived Model Contract:**
- build_model.py must produce a normalized and fully derived model
- the model must include the topology, device inventory, tenant objects, attachment expansion, derived identifiers, addressing, protocol relationships, and per-device desired state needed for rendering
- all derived values must be deterministic and reproducible from intent plus definitions

**Output:**
- derived model (JSON / in-memory)

---

### 4. Model Validation

**Module:** `pipeline/validate_model.py`

**Purpose:**
- Ensure derived model is correct and safe

**Validates:**
- uniqueness (VNI, loopbacks, router IDs)
- address overlaps
- EVPN/BGP correctness
- topology consistency
- absence of conflicting values

**Output:**
- PASS → continue
- FAIL → stop

---

### 5. Rendering

**Module:** `pipeline/render_configs.py`

**Purpose:**
- Generate full device configurations

**Responsibilities:**
- render configs using templates
- produce complete configs (not partial)
- include:
  - underlay (OSPF)
  - overlay (BGP EVPN)
  - VLAN/VNI mapping
  - VRFs
  - interfaces

**Output:**
- per-device configuration files

---

### 6. Orchestration

**Module:** `pipeline/main.py`

**Purpose:**
- Enforce correct execution order
- Prevent accidental skipping of validation stages
- Provide a single CLI entrypoint for the pipeline

---

## Module Responsibilities (Summary)

| Module | Responsibility |
|------|----------------|
| pipeline/validate_fabric_yaml.py | validate intent |
| pipeline/build_model.py | build derived model |
| pipeline/validate_model.py | validate model |
| pipeline/render_configs.py | render configs |
| pipeline/main.py | enforce execution order |

---

## Data Model Contract

Pipeline must produce:
1. parsed intent
2. normalized intent
3. derived model
4. per-device state
5. rendered configs

The derived model must be complete enough that rendering templates do not need to implement business logic.

---

## Output Artifacts

**Mandatory:**
- `outputs/model.json`
- `outputs/device_state/<device>.json`
- `outputs/configs/<device>.cfg`

**Optional:**
- validation reports
- logs

---

## Design Principles

### Separation of Concerns
- intent → desired state only
- definitions → rules and semantics
- pipeline → execution
- outputs → generated artifacts

### Deterministic Behavior
- same input → same output
- all derived values come from definitions/conventions.md

### Fail Fast
- intent validation prevents bad input
- model validation prevents bad derivation

### No Logic in YAML or Templates
- YAML contains no computed values
- templates contain no business logic

---

## Execution (CLI)

### Full pipeline (recommended)

```bash
python pipeline/main.py generate --intent intent/fabric.yaml --model-output outputs/model.json --config-dir outputs/configs
```

### Step-by-step (debug / development)

```bash
python pipeline/main.py validate-intent --intent intent/fabric.yaml
python pipeline/main.py build-model --intent intent/fabric.yaml --output outputs/model.json
python pipeline/main.py validate-model --model outputs/model.json
python pipeline/main.py render --model outputs/model.json --output-dir outputs/configs
```

---

## Summary

The pipeline guarantees:
- validated human intent
- correct derived model
- deterministic configurations

This enables safe, scalable, and repeatable EVPN fabric deployment.
