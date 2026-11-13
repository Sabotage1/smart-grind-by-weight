// SPDX-License-Identifier: MIT
function createPlugin(host) {
  "use strict";
  const id = "atom65.reaplugin", service = "5e5d6500-3f45-4b8c-9a65-28b4858d23d4";
  const commandChar = "5e5d6501-3f45-4b8c-9a65-28b4858d23d4", statusChar = "5e5d6502-3f45-4b8c-9a65-28b4858d23d4";
  const storageKey = "profile-rules-v1", devices = new Map(), sessions = new Set();
  let settings, workflow = null, config = {schema:1, devices:{}}, loaded = false, retired = false;
  let storageError = null, saving = false, saveQueue = Promise.resolve(), saveSerial = 0;
  const saveWaiters = new Map();
  const object = v => v !== null && typeof v === "object" && !Array.isArray(v);
  function fail(message, code = "invalid_argument") { const e = new Error(message); e.code = code; return e; }
  function log(error) { host.log("[atom65] " + error.message); }
  function checksum(bytes) {return bytes.reduce((s,n) => s ^ n, 0);}
  function decode(encoded) {
    const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    if (typeof encoded !== "string" || encoded.length !== 20) throw fail("Invalid Atom65 status encoding", "protocol_mismatch");
    const b = [];
    for (let i = 0; i < encoded.length; i += 4) {
      const n = [0,1,2,3].map(j => alphabet.indexOf(encoded[i+j]));
      if (n.some(value => value < 0)) throw fail("Invalid Atom65 status encoding", "protocol_mismatch");
      b.push(n[0]<<2 | n[1]>>4, (n[1]&15)<<4 | n[2]>>2, (n[2]&3)<<6 | n[3]);
    }
    if (b.length !== 15 || b[0] !== 166 || b[1] !== 1 || checksum(b.slice(0,14)) !== b[14] ||
        b[2] > 5 || (b[3] & ~15) || b[8] > 2 || b[9] > 1) throw fail("Incompatible Atom65 dose status", "protocol_mismatch");
    const word = n => b[n] | b[n+1]<<8;
    const s = {result:b[2], flags:b[3], sequence:word(4), dose:word(6)/10, slot:b[8], mode:b[9], minimum:word(10)/10, maximum:word(12)/10};
    if (s.minimum < 5 || s.maximum > 1000 || s.maximum < s.minimum || s.dose < s.minimum || s.dose > s.maximum) throw fail("Invalid Atom65 dose limits", "protocol_mismatch");
    return s;
  }
  function dose(value, status) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 5 || value > settings.MaximumDose ||
        (status && (value < status.minimum || value > status.maximum)) || Math.abs(value*10-Math.round(value*10)) > 1e-7) {
      throw fail("Dose must be 5–" + settings.MaximumDose + " g in 0.1 g steps and within the grinder's range");
    }
    return value;
  }
  function validateConfig(value) {
    if (value == null) return {schema:1, devices:{}};
    if (!object(value) || value.schema !== 1 || !object(value.devices)) throw fail("Stored profile settings are invalid; sync is paused");
    for (const [deviceId, entry] of Object.entries(value.devices)) {
      if (!deviceId.startsWith("plugin:" + id + ":atom65:") || !object(entry) || typeof entry.enabled !== "boolean" || !object(entry.rules)) throw fail("Invalid stored device settings");
      for (const [key, rule] of Object.entries(entry.rules)) {
        if (!/^[0-9a-f]{64}$/.test(key) || !object(rule) || typeof rule.title !== "string" || !["workflow","fixed"].includes(rule.mode) ||
            (rule.mode === "fixed" && (typeof rule.weight !== "number" || !Number.isFinite(rule.weight) || rule.weight < 5 || rule.weight > 1000))) throw fail("Invalid stored profile rule");
      }
    }
    return JSON.parse(JSON.stringify(value));
  }
  function current(request) {
    const deviceId = request.query && request.query.deviceId;
    if (typeof deviceId !== "string" || !devices.has(deviceId)) throw fail("Connect this Atom65 in Decaid first", "not_connected");
    return devices.get(deviceId);
  }
  function plan(state) {
    if (retired || !loaded || storageError || saving || !settings.SyncEnabled) return null;
    const profile = atomProfile(workflow), entry = config.devices[state.deviceId];
    if (!profile || !entry || !entry.enabled) return null;
    const rule = entry.rules[profile.key];
    if (!rule) return null;
    const weight = dose(rule.mode === "fixed" ? rule.weight : workflow.context && workflow.context.targetDoseWeight, state.status);
    return {key:profile.key, weight, token:profile.key + ":" + weight};
  }
  function cancel(state) { clearTimeout(state.syncTimer); state.syncTimer = null; state.desired = null; }
  function stop(state) {
    if (!state || state.stopped) return;
    state.stopped = true; state.ready = false;
    cancel(state); clearTimeout(state.watchdog);
    if (state.pending) { clearTimeout(state.pending.timer); state.pending.reject(fail("Atom65 disconnected", "stale_session")); state.pending = null; }
    sessions.delete(state);
  }
  function queue(state, force = false) {
    if (!state.ready || state.stopped) return;
    let next;
    try {next = plan(state);} catch (e) {cancel(state); state.message = e.message; return;}
    if (!next) {cancel(state); state.message = !loaded ? "Loading saved profile choices" : !settings.SyncEnabled ? "Sync paused in plugin settings" : config.devices[state.deviceId] && !config.devices[state.deviceId].enabled ? "Sync paused for this Atom65" : "Leave grinder unchanged"; return;}
    if (!force && state.desired && state.desired.token === next.token) return;
    clearTimeout(state.syncTimer); state.desired = next;
    state.message = "Dose update queued";
    state.syncTimer = setTimeout(() => {
      state.syncTimer = null;
      state.commands = state.commands.catch(() => {}).then(async () => {
        const fresh = plan(state);
        if (state.stopped || !state.ready || !fresh || state.desired !== next || fresh.token !== next.token) return;
        if (!force && state.lastApplied === next.token && state.status && state.status.dose === next.weight && state.status.slot === 2) {
          state.message = "Synced · " + next.weight + " g"; return;
        }
        await send(state, next);
      }).catch(e => { if (!state.stopped && state.desired === next) state.message = e.message; log(e); });
    }, 150);
  }
  function refresh() {for (const state of sessions) queue(state);}
  function send(state, next) {
    if (state.status.mode !== 0 || !(state.status.flags & 1) || state.status.flags & 14) {
      throw fail("Grinder busy or in time mode; return to the weight screen and tap Sync now", "busy");
    }
    const sequence = state.sequence = state.sequence % 65535 + 1, value = Math.round(next.weight*10);
    const bytes = [166,1,1,sequence&255,sequence>>8,value&255,value>>8]; bytes.push(checksum(bytes));
    let pending;
    const ack = new Promise((resolve,reject) => {pending = {sequence,resolve,reject,timer:null};});
    ack.catch(() => {});
    state.pending = pending;
    pending.timer = setTimeout(() => { if (state.pending === pending) state.pending = null; pending.reject(fail("Dose confirmation timed out; check the grinder before retrying", "timeout")); }, 2500);
    return state.session.gatt.writeWithResponse(service, commandChar, btoa(String.fromCharCode(...bytes))).then(() => ack).then(status => {
      if (state.stopped) throw fail("Retired Atom65 session", "stale_session");
      if (status.result !== 1) throw fail(["","","Grinder busy; tap Sync now when ready","Grinder rejected the dose","Select weight mode on the grinder","Dose command expired; tap Sync now"][status.result], status.result === 2 ? "busy" : "device_rejected");
      if (status.dose !== next.weight || status.slot !== 2 || status.mode !== 0) throw fail("Grinder confirmed a different dose", "protocol_mismatch");
      state.lastApplied = next.token;
      if (state.desired === next) state.message = "Synced · " + status.dose + " g";
    }).finally(() => {
      clearTimeout(pending.timer);
      if (state.pending === pending) state.pending = null;
    });
  }
  async function notification(state, encoded) {
    if (state.stopped) return;
    try {
      const status = decode(encoded); state.status = status;
      clearTimeout(state.watchdog);
      state.watchdog = setTimeout(() => {stop(state); state.message = "Bluetooth status stream stopped"; state.session.reportDisconnected().catch(log);}, 4000);
      if (state.pending && status.sequence === state.pending.sequence && status.result !== 0) {
        const pending = state.pending; state.pending = null; clearTimeout(pending.timer); pending.resolve(status);
      }
      await state.session.publish({state:status.flags & 2 ? "grinding" : "idle"});
    } catch (e) {stop(state); state.message = e.message; state.session.reportDisconnected().catch(log); throw e;}
  }
  function response(status, body) {return {status, headers:{"Content-Type":"application/json", "Cache-Control":"no-store"}, body:JSON.stringify(body)};}
  function snapshot(state, p = atomProfile(workflow)) {
    const entry = config.devices[state.deviceId] || {enabled:true, rules:{}};
    return {deviceId:state.deviceId, name:state.name, connected:state.ready && !state.stopped, loaded, storageError, saving,
      deviceEnabled:entry.enabled, syncEnabled:settings.SyncEnabled && entry.enabled, maximumDose:settings.MaximumDose, message:state.message,
      grinder:state.status, profile:p, workflowDose:workflow && workflow.context && workflow.context.targetDoseWeight,
      rule:p && entry.rules[p.key] || {mode:"leave"}, rules:Object.entries(entry.rules).map(([key,rule]) => ({key,...rule}))};
  }
  function persist(candidate) {
    const serial = ++saveSerial;
    return new Promise((resolve,reject) => {
      const timer = setTimeout(() => { saveWaiters.delete(serial); storageError = "Saving profile choices timed out; reload the plugin before syncing"; reject(fail(storageError, "storage_timeout")); }, 2500);
      saveWaiters.set(serial, {resolve, reject, timer});
      host.storage({type:"write", key:storageKey, data:{...candidate, serial}});
    });
  }
  async function configure(state, body, libraryProfile) {
    if (!loaded || storageError) throw fail(storageError || "Saved choices are still loading", "storage_unavailable");
    if (!object(body) || Object.keys(body).some(k => !["profileKey","mode","weight","enabled"].includes(k))) throw fail("Invalid profile settings");
    const p = libraryProfile || atomProfile(workflow);
    if (!p || body.profileKey !== p.key) throw fail("The selected profile changed; refresh and try again", "profile_changed");
    if (!["leave","workflow","fixed"].includes(body.mode) || typeof body.enabled !== "boolean") throw fail("Choose a profile sync mode");
    if (body.mode === "fixed") dose(body.weight, state.status);
    if (saving) throw fail("Another settings change is still saving", "busy");
    saving = true;
    for (const s of sessions) cancel(s);
    const candidate = JSON.parse(JSON.stringify(config));
    const entry = candidate.devices[state.deviceId] || {enabled:true,rules:{}};
    entry.enabled = body.enabled;
    if (body.mode === "leave") delete entry.rules[p.key];
    else entry.rules[p.key] = {title:p.title, mode:body.mode, ...(body.mode === "fixed" ? {weight:body.weight} : {})};
    candidate.devices[state.deviceId] = entry;
    try {await persist(candidate); config = candidate;} finally {saving = false; refresh();}
    return snapshot(state, p);
  }
  return {
    id, version:"0.1.1",
    onLoad(values) {
      settings = {SyncEnabled:true, MaximumDose:40, ...values};
      if (typeof settings.SyncEnabled !== "boolean" || typeof settings.MaximumDose !== "number" || !Number.isFinite(settings.MaximumDose) || settings.MaximumDose < 5 || settings.MaximumDose > 1000) throw fail("Invalid Atom65 plugin settings");
      retired = false;
      host.storage({type:"read",key:storageKey});
      return host.devices.bindDriver("atom65", {create(device) {
        const deviceId = device.id;
        if (typeof deviceId !== "string" || !deviceId.startsWith("plugin:" + id + ":atom65:")) throw fail("Unexpected Atom65 device identity");
        const state = {deviceId, name:device.name || "Atom65", ready:false, stopped:true, status:null, message:"Connect Atom65", commands:Promise.resolve()};
        devices.set(deviceId, state);
        let active;
        return {
          async connect(session) {
            if (retired) throw fail("Plugin unloaded", "stale_session");
            if (active && !active.stopped) throw fail("Atom65 is already connected", "busy");
            const s = {...state, session, stopped:false, ready:false, pending:null, desired:null, lastApplied:null, sequence:0, watchdog:null, syncTimer:null, commands:Promise.resolve()};
            active = s; devices.set(deviceId, s); sessions.add(s);
            try {
              session.gatt.onDisconnect(() => {stop(s); s.message = "Atom65 disconnected";});
              const services = await session.gatt.discoverServices();
              if (s.stopped) throw fail("Connection retired", "stale_session");
              if (!services.includes(service)) throw fail("Atom65 needs the profile-sync firmware", "protocol_mismatch");
              await session.gatt.subscribe(service, statusChar, encoded => notification(s,encoded));
              if (s.stopped) throw fail("Connection retired", "stale_session");
              await notification(s, await session.gatt.read(service,statusChar));
              if (s.stopped) throw fail("Connection retired", "stale_session");
              s.ready = true; queue(s);
            } catch (e) {stop(s); s.message = e.message; throw e;}
          },
          async disconnect() {stop(active);},
          bleEvent() {}
        };
      }});
    },
    onEvent(event) {
      if (retired) return;
      if (event.name === "workflowUpdated") {workflow = event.payload; refresh();}
      if (event.name === "storageRead" && event.payload.key === storageKey) {
        try {config = validateConfig(event.payload.value); loaded = true;} catch (e) {storageError = e.message; log(e);}
        refresh();
      }
      if (event.name === "storageWrite") {
        const pending = saveWaiters.get(event.payload && event.payload.serial);
        if (pending) {saveWaiters.delete(event.payload.serial); clearTimeout(pending.timer); pending.resolve();}
      }
    },
    onUnload() {
      retired = true;
      for (const state of sessions) stop(state);
      for (const pending of saveWaiters.values()) {clearTimeout(pending.timer); pending.reject(fail("Plugin unloaded", "stale_session"));}
      saveWaiters.clear();
    },
    async handleHttpRequest(request) {
      if (retired) return response(503,{error:"Plugin unloaded"});
      if (request.endpoint === "device-settings" && request.method === "GET") return {status:200,headers:{"Content-Type":"text/html; charset=utf-8","Cache-Control":"no-store"},body:atomSettingsPage()};
      if (request.endpoint === "skin" && request.method === "GET") return response(200,{version:1,surfaces:[{id:"atom65",kind:"header-button",label:"Atom65",action:{type:"open",view:"device-settings",presentation:"overlay"}}]});
      if (!["status","configure","sync","profile-settings"].includes(request.endpoint)) return response(404,{error:"Unknown endpoint"});
      if (request.method !== (request.endpoint === "status" ? "GET" : "POST")) return response(405,{error:"Method not allowed"});
      try {
        // An opened skin surface can omit deviceId only when there is one known grinder.
        if ((!request.query || !request.query.deviceId) && devices.size === 1) request = {...request,query:{deviceId:devices.keys().next().value}};
        const state = current(request);
        if (request.endpoint === "status") return response(200,snapshot(state));
        if (request.endpoint === "profile-settings") {
          const body = request.body;
          if (!object(body) || Object.keys(body).some(k => !["profile","choice"].includes(k))) throw fail("Invalid profile settings request");
          const p = atomProfile({profile:body.profile});
          if (!p) throw fail("Choose a named profile with recipe steps");
          // Library edits never select a workflow. The same canonical identity and
          // acknowledged storage used by Device settings remain authoritative.
          if (body.choice === undefined) return response(200,snapshot(state,p));
          if (!object(body.choice) || Object.keys(body.choice).some(k => !["profileKey","mode","weight"].includes(k))) throw fail("Invalid profile choice");
          const result = saveQueue.then(() => configure(state, {...body.choice, enabled:config.devices[state.deviceId]?.enabled ?? true}, p));
          saveQueue = result.catch(() => {}); return response(200,await result);
        }
        if (request.endpoint === "configure") {
          const result = saveQueue.then(() => configure(state, request.body));
          saveQueue = result.catch(() => {}); return response(200,await result);
        }
        if (!state.ready || state.stopped) throw fail("Connect Atom65 first", "not_connected");
        if (!plan(state)) throw fail("This profile leaves the grinder unchanged; choose and save a sync mode first");
        queue(state,true); return response(202,{queued:true});
      } catch (e) {return response(["not_connected","storage_unavailable"].includes(e.code) ? 503 : ["busy","profile_changed"].includes(e.code) ? 409 : e.code === "invalid_argument" ? 400 : 502,{error:e.message,code:e.code});}
    }
  };
}
