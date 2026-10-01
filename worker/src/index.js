const SERVER_NAME = "flight-planner-mcp";
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health")
      return Response.json({ status: "ok", server: SERVER_NAME, gateway_version: "2", timestamp: new Date().toISOString() });
    if (request.method === "POST" && url.pathname === "/e") {
      if (request.headers.get("dnt") === "1") return Response.json({ recorded: false, reason: "dnt" });
      let body; try { body = await request.json(); } catch { return Response.json({ recorded: false, reason: "invalid_json" }, { status: 400 }); }
      if (!body.schema_version) body.unregistered_event = true; // backward compat
      const props = body.properties || {};
      const cn = String(props.mcp_client_name || "");
      if (/fuzz|test|probe|monitor/i.test(cn)) return Response.json({ recorded: false, reason: "synthetic_client" });
      const payload = { event: body.event || "malformed_event", distinct_id: body.distinct_id || "unknown", properties: { ...props, mcp_server_name: props.mcp_server_name || SERVER_NAME } };
      try {
        const r = await fetch(`${env.POSTHOG_HOST || "https://us.i.posthog.com"}/capture/`, { method: "POST",
          headers: { "Content-Type": "application/json" }, body: JSON.stringify({ api_key: env.POSTHOG_API_KEY, ...payload }) });
        return Response.json({ recorded: r.ok });
      } catch (e) { return Response.json({ recorded: false, reason: "relay_error" }, { status: 502 }); }
    }
    return new Response("Not found", { status: 404 });
  }
};
