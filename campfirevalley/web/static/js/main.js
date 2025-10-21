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
    // Reset Layout button
    const resetLayoutBtn = document.getElementById('resetLayout');
    if (resetLayoutBtn) {
        resetLayoutBtn.addEventListener('click', function() {
            if (window.campfireValleyLiteGraph && window.campfireValleyLiteGraph.isInitialized) {
                window.campfireValleyLiteGraph.createDefaultNodes();
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