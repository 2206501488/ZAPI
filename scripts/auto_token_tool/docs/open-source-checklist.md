# Open Source Checklist

Before publishing this repository:

- Keep `examples/sousaku.yaml` and `examples/hotgen.yaml`; do not commit `config.yaml`.
- Keep `data/`, `runtime/`, `browser-profiles/`, and generated output ignored.
- Rotate any token or email app password that was ever committed elsewhere.
- Do not add browser profiles, cookies, local storage, screenshots, generated media, or account dumps.
- Keep target-service endpoints configurable in `service`.
- Keep local integration paths out of code. Use config fields or environment variables instead.
- Document that human verification must be completed by the operator.
- Review the target service terms before enabling chain workflows or reward claiming.
