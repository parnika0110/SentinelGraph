import { defineRailway, github, image, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const SentinelGraph = github("parnika0110/SentinelGraph");

  const falkordbVolume = volume("falkordb-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "iad", sizeMB: 500 });
  const backend = service("backend", {
    source: SentinelGraph,
    replicas: { "iad": 1 },
    build: { builder: "DOCKERFILE", dockerfilePath: "backend/Dockerfile" },
    deploy: { healthcheckPath: "/health" },
  });
  const falkordb = service("falkordb", {
    source: image("falkordb/falkordb:latest"),
    replicas: { "iad": 1 },
    volumeMounts: { "/data": falkordbVolume },
  });
  const frontend = service("frontend", {
    source: SentinelGraph,
    replicas: { "iad": 1 },
    build: { builder: "DOCKERFILE", dockerfilePath: "frontend/Dockerfile" },
    deploy: { healthcheckPath: "/" },
  });

  return project("sentinelgraph", {
    variables: { managed: false },
    resources: [backend, falkordb, frontend, falkordbVolume],
  });
});
