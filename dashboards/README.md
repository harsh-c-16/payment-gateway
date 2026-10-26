# Benchmark dashboard (Jaineel / M0)

Import [benchmark.json](benchmark.json) into the owner-managed Grafana instance.
Choose the actual Prometheus source/jobs, run context and time range. The JSON
contains no measured or sample defaults. Real import/PromQL verification is NOT_RUN.
Vichitr owns infrastructure startup and provisioning.

`python dashboards/build_dashboard.py` regenerates the definition deterministically.
See the [P5 handoff](../docs/jaineel/p5_telemetry.md) for metric bindings, limitations
and offline reconstruction without Grafana.
