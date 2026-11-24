import { app } from "../../scripts/app.js";

const css = document.createElement("link");
css.rel = "stylesheet";
css.href = new URL("./chat.css", import.meta.url).href;
document.head.append(css);

const groups = {
    Sampling: [
        ["temperature", "Temperature", 4], ["top_p", "Top P", 1], ["top_k", "Top K", 128],
        ["max_tokens", "Output token budget"], ["reasoning_budget", "Reasoning-first token budget"], ["reasoning_effort", "Provider reasoning effort"],
        ["output_format", "Answer format"],
    ],
    Media: [
        ["video_fps", "Source FPS · image batches"], ["sample_fps", "Samples per second"],
        ["max_video_frames", "Frames per video"], ["max_image_edge", "Longest edge · px"],
        ["max_visual_items", "Total visual items"], ["max_payload_mb", "Image payload · MB"],
    ],
    Request: [["stream", "Stream response"], ["timeout_seconds", "Timeout · seconds"]],
};
const presets = {
    "Server defaults": [-1, -1, -1],
    "Precise": [0.2, 0.9, 20],
    "Balanced": [0.7, 0.95, 40],
    "Creative": [1.0, 0.98, 64],
};

function element(tag, text, className) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
}

function button(label, click) {
    const el = element("button", label);
    el.type = "button";
    el.onclick = click;
    return el;
}

function openSettings(node, nodeData) {
    const dialog = element("dialog", undefined, "llml-dialog");
    dialog.setAttribute("aria-label", "Generation settings");
    const form = element("form");
    const header = element("header");
    const close = button("×", () => dialog.close());
    close.setAttribute("aria-label", "Close settings");
    header.append(element("h2", "Generation settings"), close);
    const fields = new Map();
    const tabs = element("nav");
    const body = element("section");
    for (const [group, rows] of Object.entries(groups)) {
        const page = element("div", undefined, "llml-group");
        page.hidden = group !== "Sampling";
        const tab = button(group, () => {
            for (const panel of body.children) panel.hidden = panel !== page;
            for (const item of tabs.children) item.setAttribute("aria-pressed", String(item === tab));
        });
        tab.setAttribute("aria-pressed", String(!page.hidden));
        tabs.append(tab);
        body.append(page);
        if (group === "Sampling") {
            const label = element("label", "Sampling preset", "llml-preset");
            const list = element("select");
            list.add(new Option("Apply a preset…", ""));
            for (const name of Object.keys(presets)) list.add(new Option(name));
            list.onchange = () => {
                const values = presets[list.value];
                if (values) ["temperature", "top_p", "top_k"].forEach((name, i) => {
                    const field = fields.get(name);
                    if (field && !field.linked) field.set(values[i]);
                });
                list.value = "";
            };
            label.append(list);
            page.append(label);
        }
        for (const [name, title, sliderMax] of rows) {
            const widget = node.widgets.find(w => w.name === name);
            if (!widget) continue;
            if (name === "reasoning_budget" && node.widgets.find(w => w.name === "reasoning_mode")?.value !== "llama.cpp · reasoning first") continue;
            const [type, spec] = nodeData.input.required[name] ?? nodeData.input.optional[name];
            const linked = node.inputs?.some(i => (i.widget?.name ?? i.name) === name && i.link != null);
            const row = element("div", undefined, "llml-row");
            const label = element("label", title);
            const control = element(type === "COMBO" ? "select" : "input");
            control.id = "llml-setting-" + name;
            label.htmlFor = control.id;
            row.append(label, control);
            const numeric = type === "INT" || type === "FLOAT";
            if (type === "COMBO") {
                for (const option of spec.options) control.add(new Option(option));
            } else if (numeric) {
                Object.assign(control, { type: "number", min: spec.min, max: spec.max, step: type === "INT" ? 1 : "any" });
                control.required = true;
            } else if (type === "BOOLEAN") {
                control.type = "checkbox";
            } else {
                control.type = "text";
                control.placeholder = "Server default";
                const list = element("datalist");
                list.id = control.id + "-choices";
                for (const value of ["none", "low", "medium", "high"]) list.append(new Option(value));
                control.setAttribute("list", list.id);
                row.append(list);
            }
            const get = () => type === "BOOLEAN" ? control.checked : numeric ? control.valueAsNumber : control.value;
            let slider;
            let useDefault;
            const sync = () => {
                if (slider) {
                    slider.value = Math.min(sliderMax, Math.max(0, get()));
                    slider.disabled = linked;
                }
                if (useDefault) useDefault.checked = get() < 0;
            };
            const set = value => {
                if (type === "BOOLEAN") control.checked = value;
                else control.value = value;
                sync();
            };
            if (sliderMax) {
                slider = element("input");
                Object.assign(slider, {type: "range", min: 0, max: sliderMax, step: spec.step ?? 1});
                slider.setAttribute("aria-label", title + " slider");
                slider.oninput = () => set(slider.valueAsNumber);
                row.append(slider);
            }
            if (spec.min === -1) {
                const server = element("label", undefined, "llml-server");
                useDefault = element("input");
                useDefault.type = "checkbox";
                useDefault.disabled = linked;
                useDefault.onchange = () => set(useDefault.checked ? -1 : ({temperature: 0.7, top_p: 0.95, top_k: 40, max_tokens: 4096})[name]);
                server.append(useDefault, "Server default");
                row.append(server);
            }
            control.oninput = sync;
            control.disabled = linked;
            if (linked) label.append(element("small", "Connected"));
            set(widget.value);
            fields.set(name, {widget, get, set, linked, initial: get()});
            page.append(row);
        }
    }
    const footer = element("footer");
    const apply = element("button", "Apply settings", "llml-apply");
    apply.type = "submit";
    footer.append(button("Cancel", () => dialog.close()), apply);
    form.append(header, tabs, body, footer);
    form.onsubmit = event => {
        event.preventDefault();
        node.graph?.beforeChange();
        for (const {widget, get, linked, initial} of fields.values()) {
            if (linked || get() === initial) continue;
            widget.value = get();
            widget.callback?.(widget.value, app.canvas, node);
        }
        node.graph?.afterChange();
        node.setDirtyCanvas(true, true);
        dialog.close();
    };
    // Reveal the field before the browser focuses its validation message.
    form.addEventListener("invalid", event => {
        const page = event.target.closest(".llml-group");
        if (page) tabs.children[[...body.children].indexOf(page)].click();
    }, true);
    dialog.append(form);
    dialog.onclose = () => dialog.remove();
    document.body.append(dialog);
    dialog.showModal();
}

function addReplyPanel(node, nodeData) {
    const root = element("section", undefined, "llml-reply");
    const toolbar = element("div", undefined, "llml-toolbar");
    const body = element("div", undefined, "llml-text");
    body.tabIndex = 0;
    const settings = button("Settings", () => openSettings(node, nodeData));
    settings.title = "Sampling, media and request settings";
    let reply;
    let selected = "answer";
    const answer = button("Answer", () => show("answer"));
    const reasoning = button("Reasoning", () => show("reasoning"));
    const copy = button("Copy", async () => {
        try {
            await navigator.clipboard.writeText(body.textContent);
            copy.textContent = "Copied";
        } catch {
            const range = document.createRange();
            range.selectNodeContents(body);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
            body.focus();
        }
    });
    function show(key) {
        selected = key;
        const value = reply?.[key]?.join("\n\n");
        body.textContent = value || (!reply ? "Connect an output and run the workflow to preview the reply."
            : "The server returned no reasoning. Choose Explain answer for a written rationale.");
        body.classList.toggle("llml-muted", !value);
        copy.disabled = !value;
        copy.textContent = "Copy";
        body.scrollTop = 0;
        answer.setAttribute("aria-pressed", String(key === "answer"));
        reasoning.setAttribute("aria-pressed", String(key === "reasoning"));
        reasoning.title = reply?.reasoning_mode?.[0] === "Explain answer" ? "Model-written explanation" : "Model reasoning";
        reasoning.textContent = reply?.reasoning_mode?.[0] === "Explain answer" ? "Explanation" : "Reasoning";
    }
    show("answer");
    toolbar.append(answer, reasoning, copy, settings);
    root.append(toolbar, body);
    root.addEventListener("pointerdown", e => e.stopPropagation());
    body.addEventListener("wheel", e => e.stopPropagation(), {passive: true});
    const panel = node.addDOMWidget("reply_preview", "LLMLiteReply", root, {
        serialize: false, getMinHeight: () => 112, margin: 4,
    });
    panel.serialize = false;
    const original = node.onExecuted;
    node.onExecuted = function(message, ...args) {
        const result = original?.call(this, message, ...args);
        reply = message;
        show(selected);
        return result;
    };
}

const widths = {LiteLLMChat: 390, LiteLLMProvider: 320, LiteLLMSkill: 320};
const settingsWidgets = new Set(Object.values(groups).flat().map(([name]) => name));
function inlineSettings(node) {
    const hide = !node.properties.showInlineSettings;
    for (const widget of node.widgets) {
        if (!settingsWidgets.has(widget.name)) continue;
        widget.hidden = hide;
        widget.options.hidden = hide;
    }
}

app.registerExtension({
    name: "LLMClientLite.Controls",
    getNodeMenuItems(node) {
        if (node.comfyClass !== "LiteLLMChat") return [];
        return [{
            content: node.properties.showInlineSettings ? "Hide inline settings" : "Show inline settings",
            callback: () => {
                node.properties.showInlineSettings = !node.properties.showInlineSettings;
                inlineSettings(node);
                node.setSize([node.size[0], node.computeSize()[1]]);
                node.setDirtyCanvas(true, true);
            },
        }];
    },
    beforeRegisterNodeDef(nodeType, data) {
        if (!Object.hasOwn(widths, data.name)) return;
        const original = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function(...args) {
            const result = original?.apply(this, args);
            this.color = "#24494b";
            this.bgcolor = "#202e30";
            if (data.name === "LiteLLMChat") {
                inlineSettings(this);
                addReplyPanel(this, data);
            }
            this.setSize([Math.max(widths[data.name], this.size[0]), Math.max(this.computeSize()[1], data.name === "LiteLLMChat" ? 440 : 0)]);
            return result;
        };
        if (data.name === "LiteLLMChat") {
            const configure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function(...args) {
                const result = configure?.apply(this, args);
                inlineSettings(this);
                return result;
            };
        }
    },
});
