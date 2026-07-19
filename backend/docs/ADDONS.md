# Optional add-ons

FORJD add-ons are catalog entries with config-gated clients or engine hooks.
They are disabled by default and never become core runtime dependencies merely
because they are registered.

## Enable add-ons

Use an environment override:

```dotenv
FORJD_ADDONS=osv-dev,nuclei,jax
```

Or point FORJD at YAML (relative paths resolve from `backend/`):

```dotenv
FORJD_ADDONS_CONFIG=config/addons/deml.yaml
```

```yaml
addons:
  enabled:
    - osv-dev
    - nuclei
```

`enabled: all` enables the full catalog. A non-empty `FORJD_ADDONS` always
overrides YAML. Enablement only permits execution; it does not install a large
Python package, provision credentials, or place a scanner binary on `PATH`.
Check `GET /api/v1/addons` for both `enabled` and `available` state.

The built-in profiles are:

- `config/addons/default.yaml` — everything off.
- `config/addons/deml.yaml` — everything enabled for a DEML FORJD deployment.

## Integration points

Service/tool adapters live in `app/addons/clients.py` and must call the shared
enablement gate before doing work. The ingest engine exposes three lifecycle
hook points: `before_workflow`, `after_workflow`, and `workflow_error`.

```python
from app.addons import HookPoint, register_hook


def enrich(context: Mapping[str, Any]) -> Mapping[str, Any]:
    return {"advisories": 2}


register_hook("my-addon", HookPoint.AFTER_WORKFLOW, enrich)
```

Hooks run through the `addons-run-hooks` Prefect task. Only enabled hooks run;
each failure is isolated and returned as structured status so an optional
integration cannot interrupt sealed ingest. Handlers are synchronous and must
keep secrets and plaintext out of their result payloads. Use a thin handler to
enqueue long-running work instead of blocking ingest.

## Add a new add-on

1. Add one immutable `Addon` descriptor to `app/addons/registry.py`. Choose its
   kind, source URL, availability probe, and stable lowercase slug.
2. Add a gated adapter in `clients.py`, or a small module that calls
   `register_hook`. Do not import an optional package at module load time.
3. If it is a Python package, add an explicit optional dependency group and set
   `dependency_group` on the descriptor. External tools remain image/runtime
   provisioning concerns.
4. Add the slug to `.env.example`, the catalog tests, and any opt-in profile that
   should use it. Never add it to the default profile.
5. Test disabled behavior, explicit enablement, missing availability, and hook
   failure isolation. Update this document if provisioning is non-obvious.

The catalog currently covers Acme, HoneyDB, Nuclei, Robot Framework, JAX,
OSS-Fuzz, OSV.dev, OSV-SCALIBR, go-cve-dictionary, OSV-Scanner, and the
Refactoring Guru Python patterns reference.
