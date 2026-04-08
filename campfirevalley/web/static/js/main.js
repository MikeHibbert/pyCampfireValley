// Main initialization script for CampfireValley LiteGraph interface

document.addEventListener('DOMContentLoaded', function() {
    console.log("Initializing CampfireValley LiteGraph interface...");
    
    // Wait for all dependencies to load
    if (typeof LiteGraph === 'undefined') {
        console.error("LiteGraph not found! Make sure litegraph.js is loaded.");
        return;
    }
    
    if (typeof window.campfireValleyLiteGraph === 'undefined') {
        console.error("CampfireValley LiteGraph integration not found!");
        return;
    }
    
    // Get the canvas element
    const canvas = document.getElementById('litegraphCanvas');
    if (!canvas) {
        console.error("LiteGraph canvas element not found!");
        return;
    }
    
    // Initialize the LiteGraph interface
    try {
        window.campfireValleyLiteGraph.init(canvas);
        console.log("CampfireValley LiteGraph interface initialized successfully!");
        
        // Set up header button event handlers
        setupHeaderButtons();
        
        // Handle window resize
        window.addEventListener('resize', function() {
            if (window.campfireValleyLiteGraph) {
                window.campfireValleyLiteGraph.resize();
            }
        });
        
    } catch (error) {
        console.error("Failed to initialize LiteGraph interface:", error);
    }
});

function setupHeaderButtons() {
        const showPicker = (opts) => {
        const title = (opts && opts.title) || "Select";
            const items = Array.isArray(opts && opts.items) ? opts.items : [];
        const placeholder = (opts && opts.placeholder) || "Search…";
        const initial = (opts && opts.initial) || "";
            const enableDelete = !!(opts && opts.enableDelete);
        return new Promise((resolve) => {
            const overlay = document.createElement("div");
            overlay.className = "cv-modal-overlay";
            overlay.tabIndex = -1;
            const modal = document.createElement("div");
            modal.className = "cv-modal";
            const header = document.createElement("div");
            header.className = "cv-modal-header";
            const hTitle = document.createElement("div");
            hTitle.className = "cv-modal-title";
            hTitle.textContent = title;
            const closeBtn = document.createElement("button");
            closeBtn.className = "cv-modal-close";
            closeBtn.type = "button";
            closeBtn.textContent = "×";
            header.appendChild(hTitle);
            header.appendChild(closeBtn);
            const body = document.createElement("div");
            body.className = "cv-modal-body";
            const search = document.createElement("input");
            search.className = "cv-modal-search";
            search.type = "text";
            search.placeholder = placeholder;
            search.value = initial;
            const list = document.createElement("div");
            list.className = "cv-modal-list";
            const footer = document.createElement("div");
            footer.className = "cv-modal-footer";
            const cancel = document.createElement("button");
            cancel.className = "cv-modal-btn";
            cancel.type = "button";
            cancel.textContent = "Cancel";
            const ok = document.createElement("button");
            ok.className = "cv-modal-btn primary";
            ok.type = "button";
            ok.textContent = "Load";
                const del = document.createElement("button");
                del.className = "cv-modal-btn";
                del.type = "button";
                del.textContent = "Delete";
                if (enableDelete) footer.appendChild(del);
            footer.appendChild(cancel);
            footer.appendChild(ok);
            body.appendChild(search);
            body.appendChild(list);
            modal.appendChild(header);
            modal.appendChild(body);
            modal.appendChild(footer);
            overlay.appendChild(modal);
            document.body.appendChild(overlay);
            let current = "";
            let filtered = [];
            let activeIndex = -1;
            const cleanup = (val) => {
                try {
                    document.body.removeChild(overlay);
                } catch (e) {
                }
                resolve(val);
            };
            const setActive = (idx) => {
                activeIndex = idx;
                const rows = list.querySelectorAll(".cv-modal-item");
                rows.forEach((r, i) => {
                    if (i === idx) r.classList.add("active"); else r.classList.remove("active");
                });
            };
            const nameOf = (it) => {
                if (typeof it === "string") return it;
                if (it && typeof it === "object") return it.name || "";
                return "";
            };
            const labelOf = (it) => {
                if (typeof it === "string") return it;
                if (it && typeof it === "object") {
                    const n = it.name || "";
                    const m = it.mtime ? ` • ${new Date(it.mtime).toLocaleString()}` : "";
                    const sz = (typeof it.size === "number") ? ` • ${(it.size/1024).toFixed(1)} KB` : "";
                    return n + m + sz;
                }
                return "";
            };
            const render = () => {
                const q = (search.value || "").toLowerCase().trim();
                filtered = items.filter((x) => nameOf(x).toLowerCase().includes(q));
                list.textContent = "";
                filtered.forEach((entry, idx) => {
                    const name = nameOf(entry);
                    const row = document.createElement("div");
                    row.className = "cv-modal-item";
                    row.title = String(name);
                    row.textContent = labelOf(entry);
                    row.addEventListener("click", () => {
                        current = String(name);
                        setActive(idx);
                    });
                    row.addEventListener("dblclick", () => cleanup(String(name)));
                    list.appendChild(row);
                });
                if (filtered.length === 0) {
                    const empty = document.createElement("div");
                    empty.className = "cv-modal-empty";
                    empty.textContent = "No matches";
                    list.appendChild(empty);
                    current = "";
                    setActive(-1);
                    ok.disabled = true;
                    if (enableDelete) del.disabled = true;
                    return;
                }
                ok.disabled = false;
                if (enableDelete) del.disabled = false;
                if (!current) {
                    current = String(nameOf(filtered[0]));
                    setActive(0);
                } else {
                    const i = filtered.findIndex((x) => String(nameOf(x)) === current);
                    if (i >= 0) setActive(i);
                    else {
                        current = String(nameOf(filtered[0]));
                        setActive(0);
                    }
                }
            };
            const onKey = (ev) => {
                if (ev.key === "Escape") {
                    ev.preventDefault();
                    cleanup(null);
                    return;
                }
                if (ev.key === "Enter") {
                    ev.preventDefault();
                    cleanup(current || null);
                    return;
                }
                if (ev.key === "ArrowDown") {
                    ev.preventDefault();
                    if (!filtered.length) return;
                    const next = Math.min(filtered.length - 1, (activeIndex < 0 ? 0 : activeIndex + 1));
                    current = String(filtered[next]);
                    setActive(next);
                    return;
                }
                if (ev.key === "ArrowUp") {
                    ev.preventDefault();
                    if (!filtered.length) return;
                    const next = Math.max(0, (activeIndex < 0 ? 0 : activeIndex - 1));
                    current = String(filtered[next]);
                    setActive(next);
                    return;
                }
            };
            overlay.addEventListener("keydown", onKey);
            search.addEventListener("keydown", onKey);
            list.addEventListener("keydown", onKey);
            search.addEventListener("input", render);
            closeBtn.addEventListener("click", () => cleanup(null));
            cancel.addEventListener("click", () => cleanup(null));
            ok.addEventListener("click", () => cleanup(current || null));
            if (enableDelete) {
                del.addEventListener("click", async () => {
                    const name = current || "";
                    if (!name) return;
                    try {
                        await fetch("/api/valley/delete_snapshot", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ filename: name })
                        });
                        const idx = items.findIndex((x) => String(nameOf(x)) === name);
                        if (idx >= 0) items.splice(idx, 1);
                        current = "";
                        render();
                    } catch (e) {
                    }
                });
            }
            overlay.addEventListener("mousedown", (ev) => {
                if (ev.target === overlay) cleanup(null);
            });
            render();
            setTimeout(() => {
                try {
                    search.focus();
                    search.select();
                } catch (e) {
                }
            }, 0);
        });
    };

    // Reset Layout button
    const resetLayoutBtn = document.getElementById('resetLayout');
    if (resetLayoutBtn) {
        resetLayoutBtn.addEventListener('click', function() {
            const lite = window.campfireValleyLiteGraph;
            if (!lite || !lite.isInitialized) return;
            if (typeof lite.autoArrangeRadial === "function") {
                lite.autoArrangeRadial();
                console.log("Auto-arranged layout (radial)");
            } else {
                lite.createDefaultNodes();
                console.log("Layout reset to default");
            }
        });
    }
    
    // Save Layout button
    const saveLayoutBtn = document.getElementById('saveLayout');
    if (saveLayoutBtn) {
        saveLayoutBtn.addEventListener('click', function() {
            if (window.campfireValleyLiteGraph && window.campfireValleyLiteGraph.graph) {
                try {
                    const graphData = JSON.stringify(window.campfireValleyLiteGraph.graph.serialize());
                    localStorage.setItem('campfirevalley_layout', graphData);
                    
                    // Visual feedback
                    saveLayoutBtn.textContent = '✅ Saved!';
                    setTimeout(() => {
                        saveLayoutBtn.textContent = '💾 Save Layout';
                    }, 2000);
                    
                    console.log("Layout saved to localStorage");
                } catch (error) {
                    console.error("Failed to save layout:", error);
                    
                    // Error feedback
                    saveLayoutBtn.textContent = '❌ Error';
                    setTimeout(() => {
                        saveLayoutBtn.textContent = '💾 Save Layout';
                    }, 2000);
                }
            }
        });
    }
    
    // Load Layout button
    const loadLayoutBtn = document.getElementById('loadLayout');
    if (loadLayoutBtn) {
        loadLayoutBtn.addEventListener('click', function() {
            if (window.campfireValleyLiteGraph && window.campfireValleyLiteGraph.graph) {
                try {
                    const savedLayout = localStorage.getItem('campfirevalley_layout');
                    if (savedLayout) {
                        const graphData = JSON.parse(savedLayout);
                        window.campfireValleyLiteGraph.graph.configure(graphData);
                        
                        // Visual feedback
                        loadLayoutBtn.textContent = '✅ Loaded!';
                        setTimeout(() => {
                            loadLayoutBtn.textContent = '📁 Load Layout';
                        }, 2000);
                        
                        console.log("Layout loaded from localStorage");
                    } else {
                        // No saved layout feedback
                        loadLayoutBtn.textContent = '❌ No Save';
                        setTimeout(() => {
                            loadLayoutBtn.textContent = '📁 Load Layout';
                        }, 2000);
                        
                        console.log("No saved layout found");
                    }
                } catch (error) {
                    console.error("Failed to load layout:", error);
                    
                    // Error feedback
                    loadLayoutBtn.textContent = '❌ Error';
                    setTimeout(() => {
                        loadLayoutBtn.textContent = '📁 Load Layout';
                    }, 2000);
                }
            }
        });
    }

    const saveValleyBtn = document.getElementById('saveValley');
    if (saveValleyBtn) {
        saveValleyBtn.addEventListener('click', async function() {
            const lite = window.campfireValleyLiteGraph;
            if (!lite || !lite.graph) return;
            try {
                const graph = lite.graph.serialize();
                const res = await fetch("/api/valley/save", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ graph })
                });
                if (!res.ok) throw new Error(String(res.status));
                const data = await res.json();
                saveValleyBtn.textContent = `✅ Saved`;
                setTimeout(() => {
                    saveValleyBtn.textContent = '💾 Save Valley';
                }, 2000);
                console.log("Valley saved:", data.filename);
            } catch (e) {
                console.error("Failed to save valley:", e);
                saveValleyBtn.textContent = '❌ Error';
                setTimeout(() => {
                    saveValleyBtn.textContent = '💾 Save Valley';
                }, 2000);
            }
        });
    }

    const loadValleyBtn = document.getElementById('loadValley');
    if (loadValleyBtn) {
        loadValleyBtn.addEventListener('click', async function() {
            const lite = window.campfireValleyLiteGraph;
            if (!lite || !lite.graph) return;
            try {
                const listRes = await fetch("/api/valley/snapshots");
                if (!listRes.ok) throw new Error(String(listRes.status));
                const listData = await listRes.json();
                const files = (listData && listData.snapshots) || [];
                const sorted = Array.isArray(files) ? files : [];
                const choice = await showPicker({
                    title: "Load Valley Snapshot",
                    items: sorted,
                    placeholder: "Filter snapshots…",
                    initial: (sorted[0] && (sorted[0].name || sorted[0])) || "",
                    enableDelete: true
                });
                if (!choice) return;
                const res = await fetch("/api/valley/load", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ filename: (choice.name || choice) })
                });
                if (!res.ok) throw new Error(String(res.status));
                const data = await res.json();
                if (data && data.graph) {
                    lite.graph.configure(data.graph);
                    if (typeof lite.autoArrangeRadial === "function") {
                        setTimeout(() => lite.autoArrangeRadial(), 50);
                        setTimeout(() => lite.autoArrangeRadial(), 350);
                    }
                }
                loadValleyBtn.textContent = `✅ Loaded`;
                setTimeout(() => {
                    loadValleyBtn.textContent = '📁 Load Valley';
                }, 2000);
                console.log("Valley loaded:", data.restored);
            } catch (e) {
                console.error("Failed to load valley:", e);
                loadValleyBtn.textContent = '❌ Error';
                setTimeout(() => {
                    loadValleyBtn.textContent = '📁 Load Valley';
                }, 2000);
            }
        });
    }

    const importCampfireBtn = document.getElementById('importCampfire');
    if (importCampfireBtn) {
        importCampfireBtn.addEventListener('click', function() {
            const input = document.createElement("input");
            input.type = "file";
            input.accept = ".yaml,.yml";
            input.addEventListener("change", async () => {
                const file = input.files && input.files[0];
                if (!file) return;
                try {
                    const yamlText = await file.text();
                    const res = await fetch("/api/campfire/import", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ yaml: yamlText })
                    });
                    if (!res.ok) throw new Error(String(res.status));
                    await res.json();
                    importCampfireBtn.textContent = '✅ Imported';
                    setTimeout(() => {
                        importCampfireBtn.textContent = '📥 Import Campfire';
                    }, 2000);
                    if (window.campfireValleyLiteGraph && window.campfireValleyLiteGraph.syncBackendCampfireNodes) {
                        window.campfireValleyLiteGraph.syncBackendCampfireNodes();
                    }
                } catch (e) {
                    console.error("Failed to import campfire:", e);
                    importCampfireBtn.textContent = '❌ Error';
                    setTimeout(() => {
                        importCampfireBtn.textContent = '📥 Import Campfire';
                    }, 2000);
                }
            });
            input.click();
        });
    }
}

// Global functions for external access
window.CampfireValley = {
    // Add a new campfire node
    addCampfire: function(id, position) {
        if (window.campfireValleyLiteGraph) {
            return window.campfireValleyLiteGraph.addCampfire(id, position);
        }
        return null;
    },
    
    // Add a new camper node
    addCamper: function(id, position) {
        if (window.campfireValleyLiteGraph) {
            return window.campfireValleyLiteGraph.addCamper(id, position);
        }
        return null;
    },
    
    // Remove a campfire node
    removeCampfire: function(id) {
        if (window.campfireValleyLiteGraph) {
            window.campfireValleyLiteGraph.removeCampfire(id);
        }
    },
    
    // Remove a camper node
    removeCamper: function(id) {
        if (window.campfireValleyLiteGraph) {
            window.campfireValleyLiteGraph.removeCamper(id);
        }
    },
    
    // Get the current graph state
    getGraphState: function() {
        if (window.campfireValleyLiteGraph && window.campfireValleyLiteGraph.graph) {
            return window.campfireValleyLiteGraph.graph.serialize();
        }
        return null;
    },
    
    // Set the graph state
    setGraphState: function(graphData) {
        if (window.campfireValleyLiteGraph && window.campfireValleyLiteGraph.graph) {
            window.campfireValleyLiteGraph.graph.configure(graphData);
        }
    },
    
    // Get reference to the LiteGraph instance
    getLiteGraph: function() {
        return window.campfireValleyLiteGraph;
    },
    
    // Start a task
    startTask: function(taskDescription) {
        console.log("Starting task:", taskDescription);
        
        // Send task to WebSocket if connected
        if (window.campfireValleyLiteGraph && window.campfireValleyLiteGraph.websocket && 
            window.campfireValleyLiteGraph.websocket.readyState === WebSocket.OPEN) {
            window.campfireValleyLiteGraph.websocket.send(JSON.stringify({
                type: 'start_task',
                task: taskDescription,
                timestamp: new Date().toISOString()
            }));
        }
        
        // Update task status in nodes
        if (window.campfireValleyLiteGraph && window.campfireValleyLiteGraph.nodes.taskInput) {
            window.campfireValleyLiteGraph.nodes.taskInput.properties.status = "running";
        }
        
        return true;
    },
    
    // Stop the current task
    stopTask: function() {
        console.log("Stopping current task");
        
        // Send stop signal to WebSocket if connected
        if (window.campfireValleyLiteGraph && window.campfireValleyLiteGraph.websocket && 
            window.campfireValleyLiteGraph.websocket.readyState === WebSocket.OPEN) {
            window.campfireValleyLiteGraph.websocket.send(JSON.stringify({
                type: 'stop_task',
                timestamp: new Date().toISOString()
            }));
        }
        
        // Update task status in nodes
        if (window.campfireValleyLiteGraph && window.campfireValleyLiteGraph.nodes.taskInput) {
            window.campfireValleyLiteGraph.nodes.taskInput.properties.status = "ready";
        }
        
        return true;
    }
};

// Handle page unload to clean up resources
window.addEventListener('beforeunload', function() {
    if (window.campfireValleyLiteGraph) {
        window.campfireValleyLiteGraph.destroy();
    }
});

console.log("CampfireValley main script loaded");
