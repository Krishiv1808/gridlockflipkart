document.addEventListener("DOMContentLoaded", () => {
    // API Server configuration
    const API_URL = window.location.origin;

    // App state
    let hotspots = [];
    let map = null;
    let mapMarkers = [];
    let predictionChart = null;
    let statsPollingInterval = null;
    let mapmyindiaApiKey = "";

    // Chart.js global config
    Chart.defaults.color = '#475569';
    Chart.defaults.font.family = "'Outfit', sans-serif";

    // ==========================================
    // ROLE MANAGEMENT SYSTEM
    // ==========================================
    let currentUserRole = null;

    const loginOverlay = document.getElementById("login-overlay");
    const loginViewContainer = document.getElementById("login-view-container");
    const registerViewContainer = document.getElementById("register-view-container");
    const adminLoginForm = document.getElementById("admin-login-form");
    const registerForm = document.getElementById("register-form");
    
    const btnShowAdminLogin = document.getElementById("btn-show-admin-login");
    const btnLoginCitizen = document.getElementById("btn-login-citizen");
    const btnLogout = document.getElementById("btn-logout");
    
    const linkShowRegister = document.getElementById("link-show-register");
    const linkShowLogin = document.getElementById("link-show-login");
    
    const userRoleBadge = document.getElementById("user-role-badge");
    const userRoleText = document.getElementById("user-role-text");
    const roleIcon = document.getElementById("role-icon");

    // Admin login form controls
    const adminUsernameInput = document.getElementById("admin-username");
    const adminPasswordInput = document.getElementById("admin-password");

    // Nav elements to hide/show
    const liveTabBtn = document.querySelector('[data-tab="live-tab"]');
    const analyticsTabBtn = document.querySelector('[data-tab="analytics-tab"]');
    const logsTabBtn = document.querySelector('[data-tab="logs-tab"]');

    // Toggle view listeners
    if (linkShowRegister) {
        linkShowRegister.addEventListener("click", () => {
            const errorMsgEl = document.getElementById("login-error-msg");
            const regErrorEl = document.getElementById("register-error-msg");
            if (errorMsgEl) errorMsgEl.style.display = "none";
            if (regErrorEl) regErrorEl.style.display = "none";
            loginViewContainer.style.display = "none";
            registerViewContainer.style.display = "block";
        });
    }

    if (linkShowLogin) {
        linkShowLogin.addEventListener("click", () => {
            const errorMsgEl = document.getElementById("login-error-msg");
            const regErrorEl = document.getElementById("register-error-msg");
            if (errorMsgEl) errorMsgEl.style.display = "none";
            if (regErrorEl) regErrorEl.style.display = "none";
            registerViewContainer.style.display = "none";
            loginViewContainer.style.display = "block";
        });
    }

    // Show Admin Login inputs when "Admin Sign In" is clicked
    if (btnShowAdminLogin) {
        btnShowAdminLogin.addEventListener("click", () => {
            adminLoginForm.style.display = "flex";
            btnShowAdminLogin.style.display = "none";
        });
    }

    // Citizen Login handler (Quick Access)
    if (btnLoginCitizen) {
        btnLoginCitizen.addEventListener("click", () => {
            applyUserRole("citizen");
        });
    }

    // Credentials Form Submit handler (Verifies via SQLite backend)
    if (adminLoginForm) {
        adminLoginForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const username = adminUsernameInput.value.trim();
            const password = adminPasswordInput.value;
            const errorMsgEl = document.getElementById("login-error-msg");
            if (errorMsgEl) errorMsgEl.style.display = "none";

            try {
                const res = await fetch(`${API_URL}/api/login`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, password })
                });

                if (!res.ok) {
                    const errData = await res.json();
                    if (errorMsgEl) {
                        errorMsgEl.innerText = `Login Failed: ${errData.detail || "Invalid credentials"}`;
                        errorMsgEl.style.display = "block";
                    }
                    return;
                }

                const data = await res.json();
                applyUserRole(data.role);
            } catch (error) {
                console.error("Login request failed:", error);
                if (errorMsgEl) {
                    errorMsgEl.innerText = "Server offline or database error.";
                    errorMsgEl.style.display = "block";
                }
            }
        });
    }

    // Custom Registration Form Submit handler (Saves via SQLite backend)
    if (registerForm) {
        registerForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const username = document.getElementById("reg-username").value.trim();
            const password = document.getElementById("reg-password").value;
            const role = document.getElementById("reg-role").value;
            const regErrorEl = document.getElementById("register-error-msg");
            if (regErrorEl) regErrorEl.style.display = "none";

            try {
                const res = await fetch(`${API_URL}/api/register`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, password, role })
                });

                if (!res.ok) {
                    const errData = await res.json();
                    if (regErrorEl) {
                        regErrorEl.innerText = `Registration Failed: ${errData.detail || "Username already exists"}`;
                        regErrorEl.style.display = "block";
                    }
                    return;
                }

                const data = await res.json();
                alert(`Account successfully registered as ${role.toUpperCase()}!`);
                
                // Reset fields
                document.getElementById("reg-username").value = "";
                document.getElementById("reg-password").value = "";
                
                // Reset views
                registerViewContainer.style.display = "none";
                loginViewContainer.style.display = "block";

                // Auto login
                applyUserRole(role);
            } catch (error) {
                console.error("Registration request failed:", error);
                if (regErrorEl) {
                    regErrorEl.innerText = "Server offline or database error.";
                    regErrorEl.style.display = "block";
                }
            }
        });
    }

    // Logout handler
    if (btnLogout) {
        btnLogout.addEventListener("click", () => {
            currentUserRole = null;
            // Clear credentials
            adminUsernameInput.value = "";
            adminPasswordInput.value = "";
            adminLoginForm.style.display = "none";
            btnShowAdminLogin.style.display = "block";
            
            // Stop CCTV stream on logout
            const cctvImg = document.getElementById("cctv-stream-img");
            if (cctvImg) {
                cctvImg.src = "";
            }
            
            // Show overlay and reset views
            registerViewContainer.style.display = "none";
            loginViewContainer.style.display = "block";
            loginOverlay.style.display = "flex";
        });
    }

    function applyUserRole(role) {
        currentUserRole = role;
        loginOverlay.style.display = "none";

        // Stop or start CCTV stream based on role
        const cctvImg = document.getElementById("cctv-stream-img");
        if (cctvImg) {
            if (role === "admin") {
                const camId = document.getElementById("camera-select")?.value || "CAM_021";
                cctvImg.src = `${API_URL}/api/cv_stream?camera_id=${camId}`;
                const pauseBtn = document.getElementById("btn-pause-cctv");
                const resumeBtn = document.getElementById("btn-resume-cctv");
                if (pauseBtn) pauseBtn.style.display = "block";
                if (resumeBtn) resumeBtn.style.display = "none";
            } else {
                cctvImg.src = "";
            }
        }

        if (role === "citizen") {
            // Update indicator
            userRoleBadge.style.backgroundColor = "rgba(59, 130, 246, 0.1)";
            userRoleBadge.style.borderColor = "rgba(59, 130, 246, 0.3)";
            userRoleText.innerText = "Citizen";
            userRoleText.style.color = "var(--color-blue)";
            roleIcon.className = "fa-solid fa-user-group text-blue";

            // Hide restricted tabs in navigation
            if (liveTabBtn) liveTabBtn.style.display = "none";
            if (analyticsTabBtn) analyticsTabBtn.style.display = "none";
            if (logsTabBtn) logsTabBtn.style.display = "none";

            // Switch to City Congestion Map tab automatically
            const mapBtn = document.getElementById("map-tab-btn");
            if (mapBtn) {
                mapBtn.click();
            }
            
            addLog("Logged in as Citizen. Admin dashboards disabled.", "INFO");
        } else if (role === "admin") {
            // Update indicator
            userRoleBadge.style.backgroundColor = "rgba(239, 68, 68, 0.1)";
            userRoleBadge.style.borderColor = "rgba(239, 68, 68, 0.3)";
            userRoleText.innerText = "Admin";
            userRoleText.style.color = "var(--color-red)";
            roleIcon.className = "fa-solid fa-user-shield text-red";

            // Show all tabs
            if (liveTabBtn) liveTabBtn.style.display = "flex";
            if (analyticsTabBtn) analyticsTabBtn.style.display = "flex";
            if (logsTabBtn) logsTabBtn.style.display = "flex";

            // Switch to Live CCTV Feed automatically
            if (liveTabBtn) {
                liveTabBtn.click();
            }
            
            addLog("Logged in as Administrator. Enforcement systems active.", "SUCCESS");
        }
    }

    // 1. TAB SWITCHING SYSTEM
    const navButtons = document.querySelectorAll(".nav-btn");
    const tabs = document.querySelectorAll(".tab-content");

    navButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            // Remove active classes
            navButtons.forEach(b => b.classList.remove("active"));
            tabs.forEach(t => t.classList.remove("active"));

            // Add active classes
            btn.classList.add("active");
            const tabId = btn.getAttribute("data-tab");
            const activeTab = document.getElementById(tabId);
            activeTab.classList.add("active");

            // Stop/Pause CCTV stream if switching away from live tab to save connection slots
            const cctvImg = document.getElementById("cctv-stream-img");
            const pauseBtn = document.getElementById("btn-pause-cctv");
            const resumeBtn = document.getElementById("btn-resume-cctv");
            
            if (cctvImg) {
                if (tabId === "live-tab" && currentUserRole === "admin") {
                    // Only resume if pause button is active (not manually paused)
                    if (resumeBtn && resumeBtn.style.display !== "block") {
                        const camId = document.getElementById("camera-select")?.value || "CAM_021";
                        cctvImg.src = `${API_URL}/api/cv_stream?camera_id=${camId}`;
                        if (pauseBtn) pauseBtn.style.display = "block";
                    }
                } else {
                    cctvImg.src = "";
                }
            }

            // Leaflet resize trick when map tab is activated
            if (tabId === "map-tab" && map) {
                setTimeout(() => {
                    map.invalidateSize();
                }, 100);
            }
        });
    });

    // 2. INITIALIZE DATA ON LOAD
    async function initApp() {
        try {
            // Load hotspots first (needed for map markers, dropdowns, and charts)
            await fetchHotspots();
            
            // Populate select dropdowns with loaded hotspots
            populateDropdowns();
            
            // Initialize analytics charts and start alerts polling in parallel (non-blocking)
            initAnalyticsCharts();
            startAlertsPolling();
            
            // Fetch initial dispatches and update KPIs in parallel (non-blocking)
            fetchDispatches().then(() => updateDashboardKPIs()).catch(console.error);

            // Fetch MapmyIndia API Key and initialize map in the background (non-blocking)
            mapmyindiaApiKey = localStorage.getItem("mapmyindia_api_key") || "";
            if (mapmyindiaApiKey) {
                initMap().catch(console.error);
            } else {
                fetch(`${API_URL}/api/map_key`)
                    .then(res => res.json())
                    .then(data => {
                        mapmyindiaApiKey = data.map_key || "";
                        return initMap();
                    })
                    .catch(e => {
                        console.error("Failed to load map key or initialize map:", e);
                        // Still try initializing map with empty key (Leaflet fallback)
                        initMap().catch(console.error);
                    });
            }
        } catch (error) {
            console.error("Initialization error:", error);
        }
    }

    // 3. FETCH HOTSPOTS DATA
    async function fetchHotspots() {
        try {
            const res = await fetch(`${API_URL}/api/hotspots`);
            hotspots = await res.json();
            console.log(`Loaded ${hotspots.length} hotspots.`);
        } catch (error) {
            console.error("Error fetching hotspots:", error);
            addLog("Error loading database hotspots.", "WARNING");
        }
    }

    // Update KPI panels based on loaded hotspots and dynamic database metrics
    async function updateDashboardKPIs() {
        if (hotspots.length === 0) return;
        
        // Count critical priority
        const criticalCount = hotspots.filter(h => h.priority === 'CRITICAL').length;
        document.getElementById("kpi-critical").innerText = criticalCount;
        
        // Find max speed reduction
        const maxRed = Math.max(...hotspots.map(h => h.speed_reduction));
        document.getElementById("kpi-speed").innerText = `-${(maxRed * 100).toFixed(1)}%`;
        
        // Fetch dynamic database challans count to add to base violations count
        let newChallansCount = 0;
        try {
            const res = await fetch(`${API_URL}/api/challans`);
            if (res.ok) {
                const challans = await res.json();
                newChallansCount = challans.length;
            }
        } catch (e) {
            console.error("Error fetching challans count for KPIs:", e);
        }

        // Sum total violations (base dataset + live new challans)
        const baseViols = hotspots.reduce((acc, curr) => acc + curr.total_violations, 0);
        const totalViols = baseViols + newChallansCount;
        document.getElementById("kpi-violations").innerText = totalViols.toLocaleString();
    }

    function loadMapmyIndiaSDK(key) {
        return new Promise((resolve, reject) => {
            if (window.MapmyIndia) {
                resolve();
                return;
            }
            
            // Set a safety timeout of 2.0 seconds so it never hangs page initialization
            const timeoutId = setTimeout(() => {
                cleanup();
                reject(new Error("MapmyIndia SDK load timeout"));
            }, 2000);

            const script = document.createElement("script");
            script.src = `https://apis.mapmyindia.com/advancedmaps/v1/${key}/map_load?v=1.5`;
            
            function cleanup() {
                script.onload = null;
                script.onerror = null;
                if (script.parentNode) {
                    script.parentNode.removeChild(script);
                }
            }

            script.onload = () => {
                clearTimeout(timeoutId);
                // Double check if MapmyIndia is actually available on window
                if (window.MapmyIndia) {
                    resolve();
                } else {
                    cleanup();
                    reject(new Error("MapmyIndia SDK loaded but window.MapmyIndia is undefined"));
                }
            };
            script.onerror = () => {
                clearTimeout(timeoutId);
                cleanup();
                reject(new Error("Failed to load MapmyIndia SDK"));
            };
            document.head.appendChild(script);
        });
    }

    // 4. MAP INITIALIZATION (Leaflet / MapmyIndia)
    async function initMap() {
        const mapContainer = document.getElementById("map-viewport");
        if (!mapContainer) return;

        const providerText = document.getElementById("map-provider-text");

        if (mapmyindiaApiKey) {
            if (providerText) providerText.innerText = "MapmyIndia (Premium)";
            try {
                // Try loading MapmyIndia SDK first (official way)
                await loadMapmyIndiaSDK(mapmyindiaApiKey);
                
                map = new MapmyIndia.Map("map-viewport", {
                    center: [12.9716, 77.5946],
                    zoom: 12,
                    zoomControl: true,
                    hybrid: true
                });
                console.log("MapmyIndia Map initialized successfully using SDK.");
            } catch (e) {
                console.error("MapmyIndia SDK failed to load, falling back to Leaflet Positron:", e);
                if (providerText) providerText.innerText = "Leaflet Positron (Fallback - MMI Failed)";
                
                // Initialize raw Leaflet map
                map = L.map("map-viewport").setView([12.9716, 77.5946], 12);
                
                // Load CartoDB Positron tiles (sleek light mode map layer)
                L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
                    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
                    subdomains: 'abcd',
                    maxZoom: 20
                }).addTo(map);
            }
        } else {
            if (providerText) providerText.innerText = "Leaflet Positron (Fallback)";
            // Initialize standard Leaflet Map centered on Bengaluru
            map = L.map("map-viewport").setView([12.9716, 77.5946], 12);

            // Load CartoDB Positron tiles (sleek light mode map layer)
            L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
                subdomains: 'abcd',
                maxZoom: 20
            }).addTo(map);
        }

        renderMapMarkers();
    }

    function renderMapMarkers() {
        // Clear previous markers
        mapMarkers.forEach(m => map.removeLayer(m));
        mapMarkers = [];

        const priorityColors = {
            'CRITICAL': '#ef4444',
            'HIGH': '#f59e0b',
            'NORMAL': '#10b981'
        };

        const filterVal = document.getElementById("map-filter-priority").value;
        const showTrafficLinks = document.getElementById("chk-traffic-layer").checked;

        hotspots.forEach(row => {
            // Filter logic
            if (filterVal !== "ALL" && row.priority !== filterVal) {
                if (filterVal === "HIGH" && row.priority === "NORMAL") return;
            }

            const lat = row.latitude;
            const lon = row.longitude;
            const radius = Math.max(8, Math.sqrt(row.total_violations) * 1.5);
            const color = priorityColors[row.priority];

            // Render hotspot circle
            const marker = L.circleMarker([lat, lon], {
                radius: radius,
                color: color,
                fillColor: color,
                fillOpacity: 0.65,
                weight: 1
            }).addTo(map);

            // Setup Custom Popup
            const speedLoss = 40.0 - row.actual_speed;
            const redPct = row.speed_reduction * 100;
            
            const popupContent = `
                <div class="map-popup">
                    <h4 style="color:${color}; font-weight:700; font-family:'Space Grotesk', sans-serif; margin-bottom:6px;">🚨 ${row.hotspot_id}</h4>
                    <p><b>Location:</b> ${row.location}</p>
                    <p><b>Jurisdiction:</b> ${row.police_station} PS</p>
                    <p><b>Violations Logged:</b> ${row.total_violations}</p>
                    <hr style="margin: 6px 0; border: none; border-top:1px solid #e5e7eb;">
                    <p><b>MapMyIndia Traffic Telemetry:</b></p>
                    <p>• Expected Speed: 40 km/h</p>
                    <p>• Current Speed: <span style="color:${color}; font-weight:600;">${row.actual_speed.toFixed(1)} km/h</span></p>
                    <p>• Speed Reduction: <span style="color:${color}; font-weight:600;">-${speedLoss.toFixed(1)} km/h (-${redPct.toFixed(1)}%)</span></p>
                    <hr style="margin: 6px 0; border: none; border-top:1px solid #e5e7eb;">
                    <p><b>Impact Score:</b> ${row.congestion_score}</p>
                    <p><b>Priority Rank:</b> <span style="color:${color}; font-weight:700;">${row.priority}</span></p>
                    ${currentUserRole === 'admin' ? `
                    <button class="btn btn-blue btn-small btn-full mt-2" onclick="triggerMapDispatch('${row.hotspot_id}', '${row.location}')" style="margin-top:8px;">🚀 Dispatch Wardens</button>
                    ` : `
                    <div style="font-size:0.75rem; color:#8e9bb2; font-style:italic; margin-top:8px; text-align:center; padding: 4px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius:4px;">Enforcement Actions Restricted to Admins</div>
                    `}
                </div>
            `;

            marker.bindPopup(popupContent);
            marker.bindTooltip(`${row.hotspot_id}: ${row.location.substring(0, 20)}...`);
            mapMarkers.push(marker);

            // Draw simulated congested links for Critical spots
            if (showTrafficLinks && row.priority === 'CRITICAL') {
                const offset = 0.003;
                const path = L.polyline([
                    [lat - offset, lon - offset],
                    [lat, lon],
                    [lat + offset, lon + offset]
                ], {
                    color: '#ef4444',
                    weight: 4,
                    opacity: 0.8
                }).addTo(map);
                path.bindTooltip(`Choked Road Link (-${redPct.toFixed(1)}% speed)`);
                mapMarkers.push(path);
            }
        });
    }

    // Re-draw map markers when options change
    document.getElementById("map-filter-priority").addEventListener("change", renderMapMarkers);
    document.getElementById("chk-traffic-layer").addEventListener("change", renderMapMarkers);

    // Global map dispatch caller
    window.triggerMapDispatch = function(hsId, loc) {
        if (currentUserRole !== 'admin') {
            alert("Access Denied: Citizen portal is read-only.");
            return;
        }
        dispatchEnforcement(hsId, loc, "Tow Truck Alpha");
        map.closePopup();
    };

    // 5. POPULATE DROPDOWNS
    function populateDropdowns() {
        const predictSelect = document.getElementById("predict-hotspot");
        const dispatchSelect = document.getElementById("disp-hotspot");
        const cameraSelect = document.getElementById("camera-select");
        
        if (!predictSelect || !dispatchSelect) return;

        predictSelect.innerHTML = "";
        dispatchSelect.innerHTML = "";
        if (cameraSelect) cameraSelect.innerHTML = "";

        hotspots.forEach(h => {
            const optName = `${h.hotspot_id} - ${h.location.substring(0, 32)}...`;
            
            const opt1 = document.createElement("option");
            opt1.value = h.hotspot_id;
            opt1.innerText = optName;
            predictSelect.appendChild(opt1);

            const opt2 = document.createElement("option");
            opt2.value = h.hotspot_id;
            opt2.innerText = optName;
            dispatchSelect.appendChild(opt2);

            if (cameraSelect) {
                const opt3 = document.createElement("option");
                opt3.value = h.hotspot_id;
                opt3.innerText = `${h.hotspot_id} (${h.location.substring(0, 20)}...)`;
                if (h.hotspot_id === "CAM_021") opt3.selected = true; // default to Koramangala
                cameraSelect.appendChild(opt3);
            }
        });

        // Also build the priority queue table
        renderPriorityQueue();
    }

    // 6. RENDER PRIORITY QUEUE TABLE
    function renderPriorityQueue() {
        const tbody = document.getElementById("enforcement-queue-tbody");
        if (!tbody) return;

        tbody.innerHTML = "";
        
        // Sort hotspots by score descending
        const sorted = [...hotspots].sort((a, b) => b.congestion_score - a.congestion_score);

        sorted.slice(0, 15).forEach(row => {
            const tr = document.createElement("tr");
            
            const priorityBadges = {
                'CRITICAL': '<span class="status-badge status-critical">CRITICAL</span>',
                'HIGH': '<span class="status-badge status-high">HIGH</span>',
                'NORMAL': '<span class="status-badge status-normal">NORMAL</span>'
            };

            tr.innerHTML = `
                <td><strong>${row.hotspot_id}</strong></td>
                <td>${row.location.substring(0, 45)}...</td>
                <td>${row.police_station} PS</td>
                <td><strong>${row.congestion_score}</strong></td>
                <td>${priorityBadges[row.priority]}</td>
                <td>
                    <button class="btn btn-blue btn-small" onclick="triggerQueueDispatch('${row.hotspot_id}', '${row.location.replace(/'/g, "\\'")}')">
                        <i class="fa-solid fa-truck-pickup"></i> Dispatch
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }

    window.triggerQueueDispatch = function(hsId, loc) {
        if (currentUserRole !== 'admin') {
            alert("Access Denied: Citizen portal is read-only.");
            return;
        }
        dispatchEnforcement(hsId, loc, "Traffic Patrol Team A");
    };

    // 7. REAL-TIME CCTV ALERTS POLLING
    function startAlertsPolling() {
        // Query active infractions from server every 1.5 seconds
        statsPollingInterval = setInterval(fetchCCTVAlerts, 1500);

        // Dynamic KPI and dispatch polling every 3 seconds to keep metrics in sync
        setInterval(async () => {
            await updateDashboardKPIs();
            await fetchDispatches();
        }, 3000);
    }

    async function fetchCCTVAlerts() {
        try {
            const currentCamId = document.getElementById("camera-select")?.value || "";
            const res = await fetch(`${API_URL}/api/alerts?camera_id=${currentCamId}`);
            const alerts = await res.json();
            
            const container = document.getElementById("cv-alerts-list");
            const countBadge = document.getElementById("active-alert-count");
            
            if (!container || !countBadge) return;
            
            countBadge.innerText = `${alerts.length} Active`;
            
            if (alerts.length === 0) {
                container.innerHTML = `
                    <div class="no-alerts">
                        <i class="fa-solid fa-circle-check text-green"></i>
                        <p>No parking violations currently detected.</p>
                        <span class="sub">Vehicles are moving smoothly.</span>
                    </div>
                `;
                return;
            }
            
            
            const currentRoadAlerts = [];
            const otherRoadAlerts = [];
            
            alerts.forEach(alert => {
                if (alert.location.startsWith(currentCamId)) {
                    currentRoadAlerts.push(alert);
                } else {
                    otherRoadAlerts.push(alert);
                }
            });
            
            container.innerHTML = "";
            
            // Render Current Road Section
            if (currentRoadAlerts.length > 0) {
                const secTitle = document.createElement("div");
                secTitle.className = "alert-section-title";
                secTitle.innerHTML = `<i class="fa-solid fa-location-dot text-red"></i> Current Road Violations (${currentRoadAlerts.length})`;
                container.appendChild(secTitle);
                
                currentRoadAlerts.forEach(alert => {
                    const card = createAlertCard(alert, true);
                    container.appendChild(card);
                });
            }
            
            // Render Other Roads Section
            if (otherRoadAlerts.length > 0) {
                const secTitle = document.createElement("div");
                secTitle.className = "alert-section-title";
                secTitle.style.marginTop = "15px";
                secTitle.innerHTML = `<i class="fa-solid fa-network-wired text-muted"></i> Other Roads' Violations (${otherRoadAlerts.length})`;
                container.appendChild(secTitle);
                
                otherRoadAlerts.forEach(alert => {
                    const card = createAlertCard(alert, false);
                    container.appendChild(card);
                });
            }
        } catch (error) {
            console.error("Error polling CCTV alerts:", error);
        }
    }

    function createAlertCard(alert, isCurrentRoad) {
        const card = document.createElement("div");
        card.className = "alert-card";
        if (!isCurrentRoad) {
            card.style.background = "rgba(148, 163, 184, 0.03)";
            card.style.borderColor = "rgba(148, 163, 184, 0.15)";
        }
        
        const estDelay = Math.min(15.0, alert.duration_sec * 0.1).toFixed(1);
        
        let actionButtons = "";
        if (isCurrentRoad) {
            actionButtons = `
                <button class="btn btn-blue btn-small" onclick="issueEChallan(${alert.id}, '${alert.class}', '${alert.location}')">
                    <i class="fa-solid fa-receipt"></i> Issue Challan
                </button>
                <button class="btn btn-red btn-small" onclick="dispatchTowTruck(${alert.id}, '${alert.class}', '${alert.location}')">
                    <i class="fa-solid fa-truck-pickup"></i> Tow Vehicle
                </button>
            `;
        } else {
            const camId = alert.location.split(" - ")[0];
            actionButtons = `
                <button class="btn btn-blue btn-small btn-full" onclick="switchToRoad('${camId}')">
                    <i class="fa-solid fa-video"></i> Switch to Road
                </button>
            `;
        }
        
        card.innerHTML = `
            <div class="alert-card-header">
                <h4 style="color: ${isCurrentRoad ? 'inherit' : 'var(--text-secondary)'}">⚠️ TRACKING ID: #${alert.id.toString().padStart(2, '0')} — ${alert.class.toUpperCase()}</h4>
                <span class="alert-timer" style="${isCurrentRoad ? '' : 'background: rgba(148,163,184,0.1); color: var(--text-muted); border-color: rgba(148,163,184,0.2);'}">STATIONARY ${alert.duration_sec}s</span>
            </div>
            <div class="alert-details">
                <p><b>Location:</b> ${alert.location}</p>
                <p><b>Est. Traffic Delay:</b> ${estDelay} mins</p>
            </div>
            <div class="alert-actions">
                ${actionButtons}
            </div>
        `;
        return card;
    }

    // Dispatch from CCTV Alert
    window.dispatchTowTruck = function(vehId, type, loc) {
        if (currentUserRole !== 'admin') {
            alert("Access Denied: Citizen portal is read-only.");
            return;
        }
        addLog(`Tow Truck dispatched to impound Vehicle #${vehId} (${type})`, "INFO");
        dispatchEnforcement("CAM_021", `CCTV Alert Removal (Veh #${vehId})`, "Tow Truck Alpha");
    };

    // Issue E-Challan from CCTV Alert
    window.issueEChallan = async function(vehId, type, loc) {
        if (currentUserRole !== 'admin') {
            alert("Access Denied: Citizen portal is read-only.");
            return;
        }
        try {
            const res = await fetch(`${API_URL}/api/challan`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    vehicle_id: vehId,
                    vehicle_type: type,
                    location: loc,
                    amount: 1000 // standard fine
                })
            });
            const data = await res.json();
            if (data.status === "SUCCESS") {
                addLog(`E-Challan of Rs.1000 generated for Vehicle #${vehId} (${type})`, "SUCCESS");
                updateDashboardKPIs(); // instant update of violations logged count
                alert(`Challan successfully generated for Vehicle #${vehId}!`);
            }
        } catch (error) {
            console.error("Error issuing challan:", error);
        }
    };

    // 8. DISPATCH UNIT ENDPOINT CALLS
    async function dispatchEnforcement(hotspotId, location, unitName) {
        if (currentUserRole !== 'admin') {
            alert("Access Denied: Citizen accounts cannot dispatch units.");
            return;
        }
        try {
            const res = await fetch(`${API_URL}/api/dispatch`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    hotspot_id: hotspotId,
                    location: location,
                    unit: unitName
                })
            });
            const data = await res.json();
            if (data.status === "SUCCESS") {
                addLog(`${unitName} dispatched to ${hotspotId} (${location.substring(0,25)}...)`, "SUCCESS");
                fetchDispatches(); // refresh history
                updateDashboardKPIs(); // instant update of violations/dispatches counts
                alert(`${unitName} has been successfully dispatched!`);
            }
        } catch (error) {
            console.error("Error dispatching unit:", error);
        }
    }

    // Fetch and render dispatch logs from SQLite
    async function fetchDispatches() {
        try {
            const res = await fetch(`${API_URL}/api/dispatch`);
            const dispatches = await res.json();
            
            const logsContainer = document.getElementById("system-logs-container");
            const kpiDispatches = document.getElementById("kpi-dispatches");
            
            if (kpiDispatches) {
                // Count active dispatches
                kpiDispatches.innerText = dispatches.filter(d => d.status === 'Active').length;
            }

            if (!logsContainer) return;
            
            logsContainer.innerHTML = "";
            if (dispatches.length === 0) {
                logsContainer.innerHTML = "<div class='text-muted' style='text-align:center; padding:20px;'>No dispatch activities logged.</div>";
                return;
            }

            dispatches.forEach(d => {
                const entry = document.createElement("div");
                entry.className = "log-entry log-info";
                entry.innerHTML = `[${d.timestamp}] 🚀 UNIT DISPATCHED: <strong>${d.unit}</strong> to <strong>${d.hotspot_id}</strong> (${d.location.substring(0,35)}...)`;
                logsContainer.appendChild(entry);
            });
        } catch (error) {
            console.error("Error loading dispatches:", error);
        }
    }

    // Client-side visual logging console
    function addLog(message, status = "INFO") {
        const logsContainer = document.getElementById("system-logs-container");
        if (!logsContainer) return;

        const entry = document.createElement("div");
        const statusClass = status === "SUCCESS" ? "log-success" : status === "WARNING" ? "log-warning" : "log-info";
        entry.className = `log-entry ${statusClass}`;
        entry.innerHTML = `[${new Date().toLocaleTimeString()}] ${message}`;
        
        logsContainer.insertBefore(entry, logsContainer.firstChild);
    }

    // Manual dispatch form listener
    const dispatchForm = document.getElementById("manual-dispatch-form");
    if (dispatchForm) {
        dispatchForm.addEventListener("submit", (e) => {
            e.preventDefault();
            const hsId = document.getElementById("disp-hotspot").value;
            const unit = document.getElementById("disp-unit").value;
            const loc = hotspots.find(h => h.hotspot_id === hsId).location;
            dispatchEnforcement(hsId, loc, unit);
        });
    }

    // Camera feed switcher listener
    const cameraSelect = document.getElementById("camera-select");
    const cctvStreamImg = document.getElementById("cctv-stream-img");
    if (cameraSelect && cctvStreamImg) {
        cameraSelect.addEventListener("change", (e) => {
            const camId = e.target.value;
            cctvStreamImg.src = `${API_URL}/api/cv_stream?camera_id=${camId}`;
            addLog(`Switched active CCTV feed to ${camId}`, "INFO");
            
            // Pan map to selected hotspot's coordinates
            const hs = hotspots.find(h => h.hotspot_id === camId);
            if (hs && map) {
                map.setView([hs.latitude, hs.longitude], 15);
            }
        });
    }

    // Clear logs button listener
    document.getElementById("btn-clear-logs").addEventListener("click", () => {
        const logsContainer = document.getElementById("system-logs-container");
        if (logsContainer) {
            logsContainer.innerHTML = "<div class='text-muted' style='text-align:center; padding:20px;'>Log console cleared.</div>";
        }
    });

    // MapMyIndia settings config button listener
    const btnMapSettings = document.getElementById("btn-map-settings");
    if (btnMapSettings) {
        btnMapSettings.addEventListener("click", () => {
            const currentKey = localStorage.getItem("mapmyindia_api_key") || mapmyindiaApiKey || "";
            const newKey = prompt("Configure MapmyIndia (Mappls) Integration:\n\nEnter your MapmyIndia API Key (leave empty to clear and use fallback Leaflet Positron):", currentKey);
            if (newKey !== null) {
                const trimmedKey = newKey.trim();
                if (trimmedKey) {
                    localStorage.setItem("mapmyindia_api_key", trimmedKey);
                    alert("MapmyIndia API Key saved! Reloading map...");
                } else {
                    localStorage.removeItem("mapmyindia_api_key");
                    alert("MapmyIndia Key cleared. Using Leaflet Positron fallback. Reloading map...");
                }
                window.location.reload();
            }
        });
    }

    // 9. AI PREDICTIVE FORECASTER FORM SUBMISSION
    const predictForm = document.getElementById("prediction-form");
    if (predictForm) {
        predictForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            
            const hsId = document.getElementById("predict-hotspot").value;
            const day = document.getElementById("predict-day").value;
            const hour = parseInt(document.getElementById("predict-hour").value);
            
            try {
                const res = await fetch(`${API_URL}/api/predict`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        hotspot_id: hsId,
                        day_of_week: day,
                        hour: hour
                    })
                });
                const data = await res.json();
                
                // Update KPI forecast numbers
                document.getElementById("pred-violations").innerText = `${data.expected_violations.toFixed(1)} veh`;
                document.getElementById("pred-speed-reduction").innerText = `-${data.speed_reduction_pct.toFixed(1)}%`;
                document.getElementById("pred-delay").innerText = `${data.estimated_delay_mins.toFixed(1)} mins`;
                
                // Update Badge priority
                const badge = document.getElementById("predict-badge-priority");
                badge.innerText = data.speed_reduction_pct > 40 ? "CRITICAL" : data.speed_reduction_pct > 20 ? "HIGH" : "NORMAL";
                badge.className = `badge ${data.speed_reduction_pct > 40 ? 'alert-count' : 'cam-badge'}`;
                
                // Update meta junction info
                const targetHs = hotspots.find(h => h.hotspot_id === hsId);
                const metaContainer = document.getElementById("predict-meta");
                metaContainer.innerHTML = `
                    <h5>Junction Details:</h5>
                    <ul>
                        <li><strong>Location:</strong> ${targetHs.location}</li>
                        <li><strong>Police Station:</strong> ${targetHs.police_station} PS</li>
                        <li><strong>Average Footprint W:</strong> ${targetHs.avg_weight.toFixed(2)}</li>
                        <li><strong>Standard Limit:</strong> 40 km/h</li>
                        <li><strong>Expected Velocity:</strong> ${data.predicted_speed_kmh.toFixed(1)} km/h</li>
                    </ul>
                `;
                
                // Draw chart of 24h prediction trends
                drawPredictionTrendChart(data.hourly_trends);
                addLog(`AI predicted congestion for ${hsId} on ${day} at ${hour}:00`, "SUCCESS");
            } catch (error) {
                console.error("Prediction error:", error);
                addLog("Inference failed. Machine learning model offline.", "WARNING");
            }
        });
    }

    // Update hour label on range slider change
    const hourSlider = document.getElementById("predict-hour");
    const hourLabel = document.getElementById("predict-hour-val");
    if (hourSlider && hourLabel) {
        hourSlider.addEventListener("input", (e) => {
            hourLabel.innerText = e.target.value;
        });
    }

    // Draw Chart.js prediction trend line
    function drawPredictionTrendChart(trends) {
        const ctx = document.getElementById("prediction-trend-chart").getContext("2d");
        if (!ctx) return;

        if (predictionChart) {
            predictionChart.destroy();
        }

        const labels = trends.map(t => `${t.hour.toString().padStart(2, '0')}:00`);
        const datasetSpeed = trends.map(t => t.speed_reduction_pct);
        const datasetViolations = trends.map(t => t.violations);

        predictionChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Speed Reduction %',
                        data: datasetSpeed,
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239, 68, 68, 0.05)',
                        borderWidth: 2,
                        tension: 0.3,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Violations Density',
                        data: datasetViolations,
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.05)',
                        borderWidth: 2,
                        tension: 0.3,
                        yAxisID: 'y1',
                        borderDash: [5, 5]
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top', labels: { boxWidth: 12 } }
                },
                scales: {
                    x: { grid: { color: 'rgba(0, 0, 0, 0.05)' } },
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: { display: true, text: 'Speed reduction (%)' },
                        grid: { color: 'rgba(0, 0, 0, 0.05)' }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: { display: true, text: 'Expected Vehicles' },
                        grid: { drawOnChartArea: false } // only draw grid line for left axis
                    }
                }
            }
        });
    }

    // 10. SYSTEM ANALYTICS HISTORICAL TREND CHARTS
    function initAnalyticsCharts() {
        if (hotspots.length === 0) return;

        // Chart 1: Top 10 Hotspots
        const ctxTop = document.getElementById("chart-top-hotspots").getContext("2d");
        const top10 = [...hotspots].sort((a,b) => b.congestion_score - a.congestion_score).slice(0, 10);
        
        new Chart(ctxTop, {
            type: 'bar',
            data: {
                labels: top10.map(h => `${h.hotspot_id} (${h.location.substring(0, 12)}...)`),
                datasets: [{
                    label: 'Congestion Impact Score (PCIS)',
                    data: top10.map(h => h.congestion_score),
                    backgroundColor: 'rgba(239, 68, 68, 0.75)',
                    borderColor: '#ef4444',
                    borderWidth: 1
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { color: 'rgba(0, 0, 0, 0.05)' } },
                    y: { grid: { display: false } }
                }
            }
        });

        // Chart 2: Vehicle Type Distribution
        const ctxVeh = document.getElementById("chart-vehicles").getContext("2d");
        const allVehs = {};
        hotspots.forEach(h => {
            Object.entries(h.vehicle_distribution).forEach(([k, v]) => {
                allVehs[k] = (allVehs[k] || 0) + v;
            });
        });

        new Chart(ctxVeh, {
            type: 'doughnut',
            data: {
                labels: Object.keys(allVehs),
                datasets: [{
                    data: Object.values(allVehs),
                    backgroundColor: [
                        '#3b82f6', // blue
                        '#10b981', // green
                        '#f59e0b', // orange
                        '#af52de', // purple
                        '#ef4444', // red
                        '#9ca3af'  // gray
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'right', labels: { boxWidth: 10 } }
                }
            }
        });

        // Chart 3: Temporal Hourly Distribution (Peaking Profile)
        const ctxTemp = document.getElementById("chart-temporal").getContext("2d");
        
        // We will simulate a standard 24h double-peak traffic density curve
        const hours = Array.from({length: 24}, (_, i) => `${i.toString().padStart(2, '0')}:00`);
        const morningPeak = [5, 8, 12, 22, 45, 85, 120, 140, 160, 130, 90, 80, 85, 90, 95, 110, 130, 175, 190, 180, 120, 80, 45, 15];
        const eveningPeak = [2, 5, 8, 15, 30, 60, 85, 110, 125, 115, 80, 70, 75, 80, 85, 100, 120, 145, 165, 150, 105, 75, 40, 10];
        
        new Chart(ctxTemp, {
            type: 'line',
            data: {
                labels: hours,
                datasets: [
                    {
                        label: 'Average Violations (Peak Hours)',
                        data: morningPeak,
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239, 68, 68, 0.08)',
                        fill: true,
                        tension: 0.4
                    },
                    {
                        label: 'Expected Traffic Speed Drop (km/h)',
                        data: eveningPeak.map(v => v * 0.15),
                        borderColor: '#f59e0b',
                        backgroundColor: 'rgba(245, 158, 11, 0.08)',
                        fill: true,
                        tension: 0.4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { grid: { color: 'rgba(0, 0, 0, 0.05)' } },
                    y: { grid: { color: 'rgba(0, 0, 0, 0.05)' } }
                }
            }
        });
    }

    // 11. CCTV PLAY/PAUSE SIMULATOR CONTROLS
    const pauseBtn = document.getElementById("btn-pause-cctv");
    const resumeBtn = document.getElementById("btn-resume-cctv");
    const cctvImg = document.getElementById("cctv-stream-img");

    if (pauseBtn && resumeBtn && cctvImg) {
        pauseBtn.addEventListener("click", () => {
            // Stop streaming by detaching src
            cctvImg.src = "";
            pauseBtn.style.display = "none";
            resumeBtn.style.display = "block";
            addLog("CAM_021 CCTV stream paused manually.", "INFO");
        });

        resumeBtn.addEventListener("click", () => {
            // Re-attach src to trigger new streaming boundary response
            cctvImg.src = "/api/cv_stream";
            resumeBtn.style.display = "none";
            pauseBtn.style.display = "block";
            addLog("CAM_021 CCTV stream resumed.", "INFO");
        });
    }

    // Update threshold display label
    const thresholdInput = document.getElementById("viol-threshold");
    const threshValLabel = document.getElementById("thresh-val");
    if (thresholdInput && threshValLabel) {
        thresholdInput.addEventListener("input", (e) => {
            threshValLabel.innerText = e.target.value;
        });
    }

    // Global function to switch road
    window.switchToRoad = function(camId) {
        const cameraSelect = document.getElementById("camera-select");
        if (cameraSelect) {
            cameraSelect.value = camId;
            // Dispatch change event to load stream & pan map
            const event = new Event('change');
            cameraSelect.dispatchEvent(event);
            
            // Auto switch to the live CCTV tab
            const liveTabBtn = document.querySelector('[data-tab="live-tab"]');
            if (liveTabBtn && !liveTabBtn.classList.contains("active")) {
                liveTabBtn.click();
            }
        }
    };

    // Start App Initialization
    initApp();
});
