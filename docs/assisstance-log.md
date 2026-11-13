# FulfillOps - AI Assistance Log (Section 7 Compliance)

This document records the utilization of AI assistance tools (Large Language Models) during the development, debugging, and documentation phases of the FulfillOps capstone project, in accordance with Section 7 course guidelines.

---

## 1. Summary of AI Usage Policy
AI assistance was utilized strictly as a technical collaborator for:
1. **Debugging and Pylance/Ruff Type-Checking Guidance:** Resolving strict type annotations, `Optional` checks, and linter errors.
2. **Architecture and Threat Modeling:** Structuring technical documentation, component interaction diagrams (Mermaid), and STRIDE threat matrices.
3. **Boilerplate Documentation Layouts:** Drafting professional Markdown templates for technical reports and logs.

At all stages, **all code changes were manually reviewed, tested via Pytest, validated against the public checker suite (15/15 passes), and integrated via Git pull requests.**

---

## 2. Detailed Assistance Log

| Date / Phase | Task / Area | Prompt / Assistance Type | Human Review & Verification Steps |
| :--- | :--- | :--- | :--- |
| **Phase 1: API & Worker Bug Fixes** | Pylance `None` attribute warnings in `worker.py` and 409 idempotency race condition handling | Requested code refactoring for null safety guards (`if job is None:`) and SQL row locking patterns. | Reviewed proposed python logic, verified transaction atomicity, ran local pytest suite (`pytest`), and verified 15/15 public checker passes. |
| **Phase 1: CI Lint Resolution** | Ruff (`BLE001`) and Black formatting errors in GitHub Actions | Requested specific syntax adjustments for blind exception handling (`# noqa: BLE001`) and line-ending formatting fixes. | Ran local `black` formatting and `ruff check` commands before committing and pushing to branch. |
| **Phase 2: Architecture Documentation (`docs/architecture.md`)** | System flow design and Mermaid sequence diagram generation | Requested a sequence diagram illustrating the Transactional Outbox Pattern and `SELECT ... FOR UPDATE SKIP LOCKED`. | Inspected sequence flow against implementation logic in `api/main.py` and `worker/worker.py` to ensure absolute technical accuracy. |
| **Phase 2: Threat Model (`docs/threat-model.md`)** | STRIDE threat matrix creation | Requested identification of 5 realistic distributed systems threats (overselling, poison jobs, container escape). | Mapped threats directly to existing code defenses (e.g., `with_for_update`, non-root `UID 10001`, and Trivy container security scans). |
| **Phase 2: Assistance Log (`docs/assistance-log.md`)** | Formatting the Section 7 compliance log | Generated structured template matching university capstone guidelines. | Verified adherence to Section 7 grading rules and project parameters. |

