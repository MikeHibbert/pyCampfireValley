# Federation And Dock Discovery

This repository currently demonstrates federation and remote inspection through Dock discovery.

The quickest tested path is the root Docker stack, which runs:

- a local valley on `http://localhost:8000`
- a remote demo valley on `http://localhost:8001`

## What Federation Means Here

Dock discovery allows one valley to learn about another valley without taking ownership of it.

Discovery payloads include:

- valley name
- stable valley ID
- public valley address
- dock mode
- exposed campfires
- exposed service summaries

Those service summaries are built from local service manifests and can include:

- service ID
- name
- kind and service kind
- summary
- task types
- capabilities
- rounds support
- valley-scoped addresses

## Quick Demo

From the repository root:

```bash
docker compose up -d --build
```

Then open:

- `http://localhost:8000` for the local valley
- `http://localhost:8001` for the remote demo valley

On the local UI you should be able to:

- see the remote valley in the sidebar
- see the remote valley on the graph
- open a remote campfire
- inspect visible services and visible remote campers when advertised
- message the remote campfire or add it to rounds

## Useful Discovery Endpoints

From a running valley web server:

- `GET /api/dock/status`
- `GET /api/dock/valleys`
- `GET /api/services`

## Torch Addressing

Service manifests expose addresses in two forms:

- `valley:<VALLEY_IDENTIFIER>/<SERVICE_IDENTIFIER>`
- `valley:<VALLEY_NAME>/<SERVICE_IDENTIFIER>`

Dock discovery prefers the stable valley ID when one is available.

## Remote Safety Model

Remote valleys and remote campfires are inspectable from the local UI, but remote admin actions remain disabled.

That means you can:

- inspect metadata
- read advertised capabilities
- message the remote campfire
- add the remote service to rounds

But you cannot manage the remote valley as if it were local.

## Related Docs

- [README.md](../README.md)
- [DOCKER_README.md](../DOCKER_README.md)
- [docs/web-ui.md](../docs/web-ui.md)
