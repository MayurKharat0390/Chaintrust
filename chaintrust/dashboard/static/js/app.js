/**
 * ChainTrust — Interactive Dashboard Frontend Application
 * Handles API calls, dynamic UI rendering, Chart.js graphs, and audit verification.
 */

const API_BASE = "";

// Global State
let globalAgents = [];
let globalTasks = [];
let globalAnchors = [];
let globalLeaderboard = [];
let globalComparison = [];
let globalResilience = [];
let radarChartInstance = null;
let topKChartInstance = null;
let tauChartInstance = null;

document.addEventListener("DOMContentLoaded", () => {
    initThreeDBackground();
    initAgent3DChamber();
    initDashboard();
    setupEventListeners();
});

// ---------------------------------------------------------------------------
// 0. Interactive 3D Cyberpunk Particle & Constellation Background (Three.js)
// ---------------------------------------------------------------------------
function initThreeDBackground() {
    const canvas = document.getElementById("webgl-canvas");
    if (!canvas || typeof THREE === "undefined") return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.z = 80;

    const renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    // Particle geometries (Nodes in the decentralised reputation graph)
    const particleCount = 140;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const velocities = [];

    for (let i = 0; i < particleCount; i++) {
        positions[i * 3] = (Math.random() - 0.5) * 160;
        positions[i * 3 + 1] = (Math.random() - 0.5) * 160;
        positions[i * 3 + 2] = (Math.random() - 0.5) * 100;

        velocities.push({
            x: (Math.random() - 0.5) * 0.08,
            y: (Math.random() - 0.5) * 0.08,
            z: (Math.random() - 0.5) * 0.08,
        });
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    // Glowing Cyan / Purple particle material
    const material = new THREE.PointsMaterial({
        color: 0x38bdf8,
        size: 1.8,
        transparent: true,
        opacity: 0.75,
        blending: THREE.AdditiveBlending,
    });

    const particles = new THREE.Points(geometry, material);
    scene.add(particles);

    // Interactive Mouse Tracking
    let mouseX = 0, mouseY = 0;
    window.addEventListener("mousemove", (e) => {
        mouseX = (e.clientX - window.innerWidth / 2) * 0.04;
        mouseY = (e.clientY - window.innerHeight / 2) * 0.04;
    });

    window.addEventListener("resize", () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    });

    // Animation Loop
    function animate() {
        requestAnimationFrame(animate);

        // Smooth camera dampening toward mouse position
        camera.position.x += (mouseX - camera.position.x) * 0.03;
        camera.position.y += (-mouseY - camera.position.y) * 0.03;
        camera.lookAt(scene.position);

        // Slow cinematic orbit
        particles.rotation.y += 0.0006;
        particles.rotation.x += 0.0003;

        // Animate individual node positions
        const pos = particles.geometry.attributes.position.array;
        for (let i = 0; i < particleCount; i++) {
            pos[i * 3] += velocities[i].x;
            pos[i * 3 + 1] += velocities[i].y;
            pos[i * 3 + 2] += velocities[i].z;

            // Bounce back if out of bounding cube
            if (Math.abs(pos[i * 3]) > 80) velocities[i].x *= -1;
            if (Math.abs(pos[i * 3 + 1]) > 80) velocities[i].y *= -1;
            if (Math.abs(pos[i * 3 + 2]) > 50) velocities[i].z *= -1;
        }
        particles.geometry.attributes.position.needsUpdate = true;

        renderer.render(scene, camera);
    }
    animate();
}

// ---------------------------------------------------------------------------
// 0.1 3D Cryptographic Merkle Tree Visualizer (Three.js WebGL)
// ---------------------------------------------------------------------------
let merkleScene = null;
function init3DMerkleTree() {
    const canvas = document.getElementById("merkle-3d-canvas");
    if (!canvas || typeof THREE === "undefined" || merkleScene) return;

    merkleScene = new THREE.Scene();
    const width = canvas.parentElement.clientWidth || 800;
    const height = 240;
    const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000);
    camera.position.set(0, 5, 32);

    const renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    const treeGroup = new THREE.Group();
    merkleScene.add(treeGroup);

    // Node materials
    const rootMat = new THREE.MeshBasicMaterial({ color: 0x10b981, wireframe: true });
    const branchMat = new THREE.MeshBasicMaterial({ color: 0xf59e0b, wireframe: true });
    const leafMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8, wireframe: true });
    const lineMat = new THREE.LineBasicMaterial({ color: 0x475569, transparent: true, opacity: 0.5 });

    // Root (Apex)
    const rootGeo = new THREE.OctahedronGeometry(2.2);
    const rootMesh = new THREE.Mesh(rootGeo, rootMat);
    rootMesh.position.set(0, 8, 0);
    treeGroup.add(rootMesh);

    // Layer 1 (Branches: 2 nodes)
    const branchNodes = [];
    const bGeo = new THREE.DodecahedronGeometry(1.5);
    [-8, 8].forEach((x) => {
        const bMesh = new THREE.Mesh(bGeo, branchMat);
        bMesh.position.set(x, 1, 0);
        treeGroup.add(bMesh);
        branchNodes.push(bMesh);

        // Line to root
        const lineGeo = new THREE.BufferGeometry().setFromPoints([rootMesh.position, bMesh.position]);
        treeGroup.add(new THREE.Line(lineGeo, lineMat));
    });

    // Layer 0 (Leaves: 6 nodes)
    const leafGeo = new THREE.BoxGeometry(1.2, 1.2, 1.2);
    const leafPositions = [-14, -9, -4, 4, 9, 14];
    leafPositions.forEach((x, idx) => {
        const lMesh = new THREE.Mesh(leafGeo, leafMat);
        lMesh.position.set(x, -6, (Math.random() - 0.5) * 4);
        treeGroup.add(lMesh);

        // Connect to nearest branch
        const parentBranch = idx < 3 ? branchNodes[0] : branchNodes[1];
        const lineGeo = new THREE.BufferGeometry().setFromPoints([parentBranch.position, lMesh.position]);
        treeGroup.add(new THREE.Line(lineGeo, lineMat));
    });

    // Responsive resize
    window.addEventListener("resize", () => {
        if (!canvas.parentElement) return;
        const w = canvas.parentElement.clientWidth;
        camera.aspect = w / height;
        camera.updateProjectionMatrix();
        renderer.setSize(w, height);
    });

    function animateMerkle() {
        requestAnimationFrame(animateMerkle);
        treeGroup.rotation.y += 0.008;
        rootMesh.rotation.x += 0.01;
        branchNodes.forEach(b => b.rotation.y += 0.015);
        renderer.render(merkleScene, camera);
    }
    animateMerkle();
}

async function initDashboard() {
    showToast("Loading ChainTrust telemetry...", "info");
    await Promise.allSettled([
        fetchOverviewKPIs(),
        initArenaSelectors(),
        loadLeaderboard("chs"),
        loadAlgorithmComparison(),
        loadSybilResilience(),
        loadAnchors(),
        loadTasks(),
        loadBundleList(),
        loadExperiments()
    ]);
}

function setupEventListeners() {
    // Scoring Algorithm Dropdown
    const methodSelect = document.getElementById("selectMethod");
    if (methodSelect) {
        methodSelect.addEventListener("change", (e) => {
            loadLeaderboard(e.target.value);
        });
    }

    // Recalculate Reputations Button
    const btnRecalc = document.getElementById("btnRecalculate");
    if (btnRecalc) {
        btnRecalc.addEventListener("click", async () => {
            btnRecalc.disabled = true;
            btnRecalc.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>Computing...`;
            try {
                const res = await fetch(`${API_BASE}/api/reputation/compute`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ epoch: 1 })
                });
                if (res.ok) {
                    showToast("Reputation scores recomputed successfully!", "success");
                    await loadLeaderboard(document.getElementById("selectMethod")?.value || "chs");
                    await loadAlgorithmComparison();
                } else {
                    showToast("Failed to recompute scores.", "danger");
                }
            } catch (err) {
                showToast("API connection error: " + err.message, "danger");
            } finally {
                btnRecalc.disabled = false;
                btnRecalc.innerHTML = `<i class="fa-solid fa-arrows-rotate me-2"></i>Recalculate Reputations`;
            }
        });
    }

    // Tab Switch: Trigger 3D Merkle Tree initialization when audit tab is shown
    const auditTabBtn = document.getElementById("tab-audit-btn");
    if (auditTabBtn) {
        auditTabBtn.addEventListener("shown.bs.tab", () => {
            init3DMerkleTree();
        });
    }

    // Run Sybil Benchmark Button
    const btnSybil = document.getElementById("btnRunSybil");
    if (btnSybil) {
        btnSybil.addEventListener("click", async () => {
            btnSybil.disabled = true;
            btnSybil.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>Simulating...`;
            try {
                const res = await fetch(`${API_BASE}/api/experiments/resilience?refresh=true`);
                if (res.ok) {
                    showToast("Sybil benchmark completed and saved!", "success");
                    await loadSybilResilience();
                } else {
                    showToast("Failed to run benchmark.", "danger");
                }
            } catch (err) {
                showToast("API connection error: " + err.message, "danger");
            } finally {
                btnSybil.disabled = false;
                btnSybil.innerHTML = `<i class="fa-solid fa-bolt me-2"></i>Run Sybil Benchmark`;
            }
        });
    }

    // Verify Bundle Button
    const btnVerify = document.getElementById("btnVerifyBundle");
    if (btnVerify) {
        btnVerify.addEventListener("click", handleVerifyBundle);
    }

    // SFX Synthesizer Toggle Button
    const btnSFX = document.getElementById("btnToggleSFX");
    if (btnSFX) {
        btnSFX.addEventListener("click", toggleSFX);
    }

    // 3D Chamber Action Buttons
    const btnWarp = document.getElementById("btn3dWarpIn");
    if (btnWarp) {
        btnWarp.addEventListener("click", () => {
            const agentSelect = document.getElementById("arenaAgentSelect");
            const agentId = agentSelect ? agentSelect.value : null;
            const ag = globalAgents.find(a => a.agent_id === agentId) || globalAgents[0];
            triggerAgentWarpEntrance(ag);
        });
    }

    const btnRotate = document.getElementById("btn3dRotate");
    if (btnRotate) {
        btnRotate.addEventListener("click", () => {
            isAutoOrbit = !isAutoOrbit;
            btnRotate.classList.toggle("active", isAutoOrbit);
            btnRotate.innerHTML = `<i class="fa-solid fa-arrows-spin me-1"></i>Orbit`;
        });
    }

    const btnReset = document.getElementById("btn3dReset");
    if (btnReset) {
        btnReset.addEventListener("click", resetChamberCamera);
    }

    const btnInspect = document.getElementById("btn3dInspect");
    if (btnInspect) {
        btnInspect.addEventListener("click", focusChamberCore);
    }

    // Code Studio Buttons
    const btnCopy = document.getElementById("btnCopySnippet");
    if (btnCopy) {
        btnCopy.addEventListener("click", () => {
            if (!currentCodeText) {
                showToast("No code snippet to copy yet.", "warning");
                return;
            }
            navigator.clipboard.writeText(currentCodeText);
            showToast("Python solution copied to clipboard!", "success");
        });
    }

    const btnReplay = document.getElementById("btnReplayStream");
    if (btnReplay) {
        btnReplay.addEventListener("click", () => {
            if (!currentCodeText) {
                showToast("Run agent dispatch first to stream code.", "info");
                return;
            }
            startCodeStreaming(currentCodeText, currentCodeTokens, currentCodeLatency);
        });
    }

    const btnInstant = document.getElementById("btnInstantView");
    if (btnInstant) {
        btnInstant.addEventListener("click", () => {
            if (!currentCodeText) return;
            renderCodeInstant(currentCodeText);
        });
    }

    // Tab Switch: Trigger 3D Chamber resize when arena tab is activated
    const arenaTabBtn = document.getElementById("tab-arena-btn");
    if (arenaTabBtn) {
        arenaTabBtn.addEventListener("shown.bs.tab", () => {
            resizeAgent3DChamber();
        });
    }
}

// ---------------------------------------------------------------------------
// 1. Overview KPIs
// ---------------------------------------------------------------------------
async function fetchOverviewKPIs() {
    try {
        const [resAgents, resTasks, resAnchors] = await Promise.all([
            fetch(`${API_BASE}/api/agents`),
            fetch(`${API_BASE}/api/tasks?limit=1000`),
            fetch(`${API_BASE}/api/anchors`)
        ]);

        if (resAgents.ok) {
            globalAgents = await resAgents.json();
            document.getElementById("kpiAgents").innerText = globalAgents.length;
        }
        if (resTasks.ok) {
            globalTasks = await resTasks.json();
            document.getElementById("kpiTasks").innerText = globalTasks.length;
        }
        if (resAnchors.ok) {
            globalAnchors = await resAnchors.json();
            document.getElementById("kpiAnchors").innerText = globalAnchors.length;
        }

        document.getElementById("kpiInteractions").innerText = (globalAgents.length * 40) || 240;
    } catch (e) {
        console.error("Error loading KPIs", e);
    }
}

// ---------------------------------------------------------------------------
// 2. Leaderboard
// ---------------------------------------------------------------------------
async function loadLeaderboard(method = "chs") {
    const tbody = document.getElementById("leaderboardBody");
    const thead = document.getElementById("leaderboardHead");
    if (!tbody) return;

    if (method === "chs") {
        if (thead) {
            thead.innerHTML = `
                <tr>
                    <th style="width: 70px;">Rank</th>
                    <th>Agent Label / ID</th>
                    <th>Provider & Model</th>
                    <th class="text-end">D' (Evidence)</th>
                    <th class="text-end">C_a (Conf)</th>
                    <th class="text-end">T~ (Trust)</th>
                    <th class="text-end">&pi; (Defense)</th>
                    <th class="text-end" style="min-width: 170px;">CHS Score</th>
                </tr>
            `;
        }
        tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-muted"><span class="spinner-border spinner-border-sm me-2"></span>Loading CHS leaderboard & component breakdown...</td></tr>`;

        try {
            const res = await fetch(`${API_BASE}/api/reputation/chs/breakdown`);
            if (!res.ok) throw new Error("CHS breakdown API returned error");
            const data = await res.json();
            const agents = data.agents || [];
            globalLeaderboard = agents;

            if (agents.length === 0) {
                tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-muted">No CHS records found. Click 'Recalculate Reputations' to compute.</td></tr>`;
                return;
            }

            tbody.innerHTML = agents.map((item, index) => {
                const rank = index + 1;
                const rankClass = rank === 1 ? "rank-1" : (rank === 2 ? "rank-2" : (rank === 3 ? "rank-3" : "rank-other"));
                const providerClass = `badge-${(item.provider || "default").toLowerCase()}`;
                const pct = (item.score * 100).toFixed(1);

                return `
                    <tr>
                        <td><span class="badge-rank ${rankClass}">${rank}</span></td>
                        <td>
                            <div class="fw-bold">${escapeHtml(item.name)}</div>
                            <div class="small text-secondary font-monospace">${item.agent_id.substring(0, 16)}...</div>
                        </td>
                        <td>
                            <div><span class="badge-provider ${providerClass}">${escapeHtml(item.provider)}</span></div>
                            <div class="small text-light mt-1">${escapeHtml(item.model)}</div>
                        </td>
                        <td class="text-end font-monospace text-light">${item.d_prime.toFixed(4)}</td>
                        <td class="text-end font-monospace text-info">${item.c_a.toFixed(4)}</td>
                        <td class="text-end font-monospace text-primary">${item.t_tilde.toFixed(4)}</td>
                        <td class="text-end font-monospace ${item.pi_a > 0 ? 'text-danger fw-bold' : 'text-success'}">${item.pi_a > 0 ? '-' + item.pi_a.toFixed(4) : '0.0000'}</td>
                        <td class="text-end" style="min-width: 170px;">
                            <div class="d-flex align-items-center justify-content-between mb-1">
                                <span class="fw-bold text-warning">${item.score.toFixed(4)}</span>
                                <span class="small text-muted">${pct}%</span>
                            </div>
                            <div class="progress" style="height: 6px; background-color: rgba(255,255,255,0.06);">
                                <div class="progress-bar bg-warning" role="progressbar" style="width: ${pct}%"></div>
                            </div>
                        </td>
                    </tr>
                `;
            }).join("");

        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-danger">Error loading CHS leaderboard: ${e.message}</td></tr>`;
        }

    } else {
        if (thead) {
            thead.innerHTML = `
                <tr>
                    <th style="width: 70px;">Rank</th>
                    <th>Agent Label / ID</th>
                    <th>Provider</th>
                    <th>Model</th>
                    <th>Stake</th>
                    <th>Reputation Score</th>
                </tr>
            `;
        }
        tbody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-muted"><span class="spinner-border spinner-border-sm me-2"></span>Loading leaderboard...</td></tr>`;

        try {
            const res = await fetch(`${API_BASE}/api/reputation/leaderboard?method=${method}`);
            if (!res.ok) throw new Error("Leaderboard API returned error");
            const data = await res.json();
            globalLeaderboard = data;

            if (data.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-muted">No records found for ${method}. Click 'Recalculate Reputations' to compute.</td></tr>`;
                return;
            }

            tbody.innerHTML = data.map((item, index) => {
                const rank = index + 1;
                const rankClass = rank === 1 ? "rank-1" : (rank === 2 ? "rank-2" : (rank === 3 ? "rank-3" : "rank-other"));
                const providerClass = `badge-${(item.provider || "default").toLowerCase()}`;
                const pct = (item.score * 100).toFixed(1);

                return `
                    <tr>
                        <td><span class="badge-rank ${rankClass}">${rank}</span></td>
                        <td>
                            <div class="fw-bold">${escapeHtml(item.name)}</div>
                            <div class="small text-secondary font-monospace">${item.agent_id.substring(0, 16)}...</div>
                        </td>
                        <td><span class="badge-provider ${providerClass}">${escapeHtml(item.provider)}</span></td>
                        <td><span class="small text-light">${escapeHtml(item.model)}</span></td>
                        <td><span class="badge bg-dark border border-secondary">${item.stake !== undefined ? item.stake : 10}</span></td>
                        <td style="min-width: 180px;">
                            <div class="d-flex align-items-center justify-content-between mb-1">
                                <span class="fw-bold text-info">${item.score.toFixed(4)}</span>
                                <span class="small text-muted">${pct}%</span>
                            </div>
                            <div class="progress" style="height: 6px; background-color: rgba(255,255,255,0.06);">
                                <div class="progress-bar bg-info" role="progressbar" style="width: ${pct}%"></div>
                            </div>
                        </td>
                    </tr>
                `;
            }).join("");

        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-danger">Error loading leaderboard: ${e.message}</td></tr>`;
        }
    }
}

// ---------------------------------------------------------------------------
// 3. Algorithm Comparison (Table + Chart.js)
// ---------------------------------------------------------------------------
async function loadAlgorithmComparison() {
    const tbody = document.getElementById("comparisonBody");
    if (!tbody) return;

    try {
        const res = await fetch(`${API_BASE}/api/reputation/comparison`);
        if (!res.ok) return;
        const data = await res.json();
        const agents = data.agents || [];
        globalComparison = agents;

        if (agents.length === 0) return;

        tbody.innerHTML = agents.map(ag => {
            const s = ag.scores || {};
            const tr = s.tracerank !== undefined ? s.tracerank.toFixed(4) : "-";
            const et = s.eigentrust !== undefined ? s.eigentrust.toFixed(4) : "-";
            const pr = s.pagerank !== undefined ? s.pagerank.toFixed(4) : "-";
            const wt = s.weighted !== undefined ? s.weighted.toFixed(4) : "-";
            const sa = s.simple_avg !== undefined ? s.simple_avg.toFixed(4) : "-";

            return `
                <tr>
                    <td class="fw-bold text-light">${escapeHtml(ag.name)}</td>
                    <td class="text-end fw-bold text-info">${tr}</td>
                    <td class="text-end text-light">${et}</td>
                    <td class="text-end text-light">${pr}</td>
                    <td class="text-end text-light">${wt}</td>
                    <td class="text-end text-light">${sa}</td>
                </tr>
            `;
        }).join("");

        renderComparisonChart(agents);

    } catch (e) {
        console.error("Error loading comparison", e);
    }
}

function renderComparisonChart(agents) {
    const ctx = document.getElementById("comparisonChart");
    if (!ctx) return;

    if (radarChartInstance) {
        radarChartInstance.destroy();
    }

    const labels = agents.map(a => a.name);
    const traceRankData = agents.map(a => a.scores.tracerank || 0);
    const simpleAvgData = agents.map(a => a.scores.simple_avg || 0);
    const eigenTrustData = agents.map(a => a.scores.eigentrust || 0);

    radarChartInstance = new Chart(ctx, {
        type: "bar",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "TraceRank (Proprietary)",
                    data: traceRankData,
                    backgroundColor: "rgba(56, 189, 248, 0.75)",
                    borderColor: "#38bdf8",
                    borderWidth: 1
                },
                {
                    label: "Simple Average (Baseline)",
                    data: simpleAvgData,
                    backgroundColor: "rgba(148, 163, 184, 0.4)",
                    borderColor: "#94a3b8",
                    borderWidth: 1
                },
                {
                    label: "EigenTrust",
                    data: eigenTrustData,
                    backgroundColor: "rgba(168, 85, 247, 0.6)",
                    borderColor: "#a855f7",
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 1.0,
                    grid: { color: "rgba(255, 255, 255, 0.05)" },
                    ticks: { color: "#94a3b8" }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: "#94a3b8" }
                }
            },
            plugins: {
                legend: { labels: { color: "#f8fafc", font: { family: "Inter" } } }
            }
        }
    });
}

// ---------------------------------------------------------------------------
// 4. Sybil Resilience Benchmark (Chart.js)
// ---------------------------------------------------------------------------
async function loadSybilResilience() {
    try {
        const res = await fetch(`${API_BASE}/api/experiments/resilience`);
        if (!res.ok) return;
        const data = await res.json();
        globalResilience = data;

        renderSybilCharts(data);
    } catch (e) {
        console.error("Error loading Sybil resilience", e);
    }
}

function renderSybilCharts(data) {
    const ctxTopK = document.getElementById("topKChart");
    const ctxTau = document.getElementById("tauChart");
    if (!ctxTopK || !ctxTau || !data.length) return;

    if (topKChartInstance) topKChartInstance.destroy();
    if (tauChartInstance) tauChartInstance.destroy();

    const cloneCounts = data.map(d => d.clone_count);
    const methods = ["chs", "tracerank", "eigentrust", "pagerank", "simple_avg"];
    const colors = {
        chs: "#f59e0b",
        tracerank: "#38bdf8",
        eigentrust: "#a855f7",
        pagerank: "#10b981",
        simple_avg: "#ef4444"
    };

    const topKDatasets = methods.map(m => ({
        label: m.toUpperCase(),
        data: data.map(d => (d.metrics[m] ? d.metrics[m].top_k_preserved : 0)),
        borderColor: colors[m],
        backgroundColor: colors[m],
        tension: 0.2,
        borderWidth: 2
    }));

    const tauDatasets = methods.map(m => ({
        label: m.toUpperCase(),
        data: data.map(d => (d.metrics[m] ? d.metrics[m].kendall_tau : 0)),
        borderColor: colors[m],
        backgroundColor: colors[m],
        tension: 0.2,
        borderWidth: 2
    }));

    topKChartInstance = new Chart(ctxTopK, {
        type: "line",
        data: { labels: cloneCounts, datasets: topKDatasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { min: -0.1, max: 1.1, grid: { color: "rgba(255, 255, 255, 0.05)" }, ticks: { color: "#94a3b8" } },
                x: { title: { display: true, text: "Sybil Clones Injected", color: "#94a3b8" }, ticks: { color: "#94a3b8" } }
            },
            plugins: { legend: { labels: { color: "#f8fafc" } } }
        }
    });

    tauChartInstance = new Chart(ctxTau, {
        type: "line",
        data: { labels: cloneCounts, datasets: tauDatasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { min: -0.1, max: 1.1, grid: { color: "rgba(255, 255, 255, 0.05)" }, ticks: { color: "#94a3b8" } },
                x: { title: { display: true, text: "Sybil Clones Injected", color: "#94a3b8" }, ticks: { color: "#94a3b8" } }
            },
            plugins: { legend: { labels: { color: "#f8fafc" } } }
        }
    });
}

// ---------------------------------------------------------------------------
// 5. Blockchain Anchors & Bundles
// ---------------------------------------------------------------------------
async function loadAnchors() {
    const tbody = document.getElementById("anchorsBody");
    if (!tbody) return;

    try {
        const res = await fetch(`${API_BASE}/api/anchors`);
        if (!res.ok) return;
        const anchors = await res.json();

        if (anchors.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">No blockchain anchors recorded yet.</td></tr>`;
            return;
        }

        tbody.innerHTML = anchors.map(a => `
            <tr>
                <td class="fw-bold text-info">${a.epoch}</td>
                <td><span class="small font-monospace text-light">${a.agent_id.substring(0, 16)}...</span></td>
                <td><span class="small font-monospace text-warning">${a.merkle_root.substring(0, 20)}...</span></td>
                <td><span class="small font-monospace text-secondary">${a.tx_hash ? a.tx_hash.substring(0, 18) + '...' : 'Simulated (0x...)'}</span></td>
                <td><span class="badge bg-dark border border-info">Block #${a.block_number || 1001}</span></td>
            </tr>
        `).join("");

    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-danger">Error loading anchors</td></tr>`;
    }
}

async function loadBundleList() {
    const select = document.getElementById("selectBundle");
    if (!select) return;

    try {
        const res = await fetch(`${API_BASE}/api/bundles`);
        if (res.ok) {
            const bundles = await res.json();
            if (bundles.length > 0) {
                select.innerHTML = bundles.map(b => `<option value="${b}">${b}</option>`).join("");
            } else {
                select.innerHTML = `<option value="">No bundles found on disk</option>`;
            }
        }
    } catch (e) {
        console.error("Error loading bundle list", e);
    }
}

async function handleVerifyBundle() {
    const fileInput = document.getElementById("bundleFileInput");
    const select = document.getElementById("selectBundle");
    const filename = select ? select.value : "";
    const resultsContainer = document.getElementById("verifyResults");
    if (!resultsContainer) return;

    let bundleData = null;
    let sourceLabel = "";

    if (fileInput && fileInput.files && fileInput.files.length > 0) {
        try {
            const file = fileInput.files[0];
            const text = await file.text();
            bundleData = JSON.parse(text);
            sourceLabel = `Uploaded file: ${file.name}`;
        } catch (e) {
            resultsContainer.innerHTML = `<div class="alert alert-danger">Invalid JSON in uploaded file: ${escapeHtml(e.message)}</div>`;
            return;
        }
    } else if (filename) {
        try {
            resultsContainer.innerHTML = `<div class="text-center py-4 text-info"><span class="spinner-border spinner-border-sm me-2"></span>Fetching bundle ${escapeHtml(filename)}...</div>`;
            const bundleRes = await fetch(`${API_BASE}/api/bundles/${filename}`);
            if (!bundleRes.ok) throw new Error("Could not fetch bundle content");
            bundleData = await bundleRes.json();
            sourceLabel = `Repo bundle: ${filename}`;
        } catch (e) {
            resultsContainer.innerHTML = `<div class="alert alert-danger">Error fetching bundle: ${escapeHtml(e.message)}</div>`;
            return;
        }
    } else {
        showToast("Please choose a bundle or select an existing one.", "warning");
        return;
    }

    resultsContainer.innerHTML = `<div class="text-center py-4 text-info"><span class="spinner-border spinner-border-sm me-2"></span>Performing cryptographic verification & score recomputation...</div>`;

    try {
        const checkOnChain = document.getElementById("checkOnChain")?.checked || false;

        const verifyRes = await fetch(`${API_BASE}/api/verify`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ bundle: bundleData, check_on_chain: checkOnChain })
        });

        if (!verifyRes.ok) throw new Error("Verification API failed");
        const res = await verifyRes.json();

        const statusBadge = (val) => val === true ? `<span class="badge-pass"><i class="fa-solid fa-check me-1"></i>PASS</span>` : (val === false ? `<span class="badge-fail"><i class="fa-solid fa-xmark me-1"></i>FAIL</span>` : `<span class="badge bg-secondary">SKIPPED</span>`);

        let levelBadge = "";
        if (res.level_b_valid === true) {
            levelBadge = `<span class="badge bg-success ms-2"><i class="fa-solid fa-shield-halved me-1"></i>Level B Verified</span>`;
        } else if (res.level_a_valid === true) {
            levelBadge = `<span class="badge bg-primary ms-2"><i class="fa-solid fa-shield me-1"></i>Level A Verified</span>`;
        }

        let breakdownDetails = "";
        if (res.direct_score !== undefined && (res.confidence > 0 || res.t_tilde > 0)) {
            breakdownDetails = `
                <div class="mt-2 p-2 rounded bg-dark border border-secondary small">
                    <div class="text-white fw-bold mb-1">Recomputed CHS Components:</div>
                    <div class="d-flex flex-wrap gap-2 text-secondary font-monospace">
                        <span>D': <strong class="text-light">${res.direct_score.toFixed(4)}</strong></span> |
                        <span>C_a: <strong class="text-info">${res.confidence.toFixed(4)}</strong></span> |
                        <span>T~: <strong class="text-primary">${res.t_tilde.toFixed(4)}</strong></span> |
                        <span>&pi;: <strong class="${res.defense_penalty > 0 ? 'text-danger' : 'text-success'}">${res.defense_penalty.toFixed(4)}</strong></span>
                    </div>
                </div>
            `;
        }

        let errorsHtml = "";
        if (res.errors && res.errors.length > 0) {
            errorsHtml = `
                <div class="mt-2 p-2 rounded bg-danger bg-opacity-10 border border-danger small text-danger">
                    <div class="fw-bold mb-1"><i class="fa-solid fa-triangle-exclamation me-1"></i>Verification Anomalies:</div>
                    <ul class="mb-0 ps-3">
                        ${res.errors.map(e => `<li>${escapeHtml(e)}</li>`).join("")}
                    </ul>
                </div>
            `;
        }

        resultsContainer.innerHTML = `
            <div class="alert ${res.valid ? 'alert-success bg-opacity-10 border-success' : 'alert-danger bg-opacity-10 border-danger'} mb-3">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <h5 class="fw-bold mb-0">${res.valid ? '✅ AUDIT VERIFICATION PASSED' : '❌ AUDIT VERIFICATION FAILED'}</h5>
                    ${levelBadge}
                </div>
                <div class="small">${res.valid ? 'The audit bundle is mathematically and cryptographically authentic!' : 'Tampering or calculation mismatch detected.'}</div>
                <div class="small text-muted mt-1 font-monospace">${escapeHtml(sourceLabel)}</div>
            </div>

            <div class="verify-item">
                <span>1. Canonical Record Leaf Hashing</span>
                ${statusBadge(res.leaves_valid)}
            </div>
            <div class="verify-item">
                <span>2. Merkle Root Reconstruction</span>
                ${statusBadge(res.merkle_root_valid)}
            </div>
            <div class="verify-item">
                <span>3. Cryptographic Inclusion Proofs</span>
                ${statusBadge(res.proofs_valid)}
            </div>
            ${res.difficulty_root_valid !== null ? `
            <div class="verify-item">
                <span>4. Task Difficulty Root Commitment</span>
                ${statusBadge(res.difficulty_root_valid)}
            </div>` : ''}
            ${res.params_hash_valid !== null ? `
            <div class="verify-item">
                <span>5. CHS Parameters Hash Commitment</span>
                ${statusBadge(res.params_hash_valid)}
            </div>` : ''}
            ${res.confidence_valid !== null ? `
            <div class="verify-item">
                <span>6. Consistency Confidence Factor (C_a)</span>
                ${statusBadge(res.confidence_valid)}
            </div>` : ''}
            ${res.ratings_root_valid !== null ? `
            <div class="verify-item">
                <span>7. Peer Ratings Merkle Root (Level B)</span>
                ${statusBadge(res.ratings_root_valid)}
            </div>` : ''}
            <div class="verify-item">
                <span>8. Score Recomputation (${res.claimed_score.toFixed(4)} vs ${res.recomputed_score.toFixed(4)})</span>
                ${statusBadge(res.score_recomputed_valid)}
            </div>
            ${breakdownDetails}
            <div class="verify-item mt-2">
                <span>9. Score Commitment Hash</span>
                ${statusBadge(res.score_hash_valid)}
            </div>
            ${checkOnChain ? `
            <div class="verify-item">
                <span>10. On-Chain Anchor Commitment</span>
                ${statusBadge(res.on_chain_valid)}
            </div>` : ''}
            ${errorsHtml}
        `;

    } catch (err) {
        resultsContainer.innerHTML = `<div class="alert alert-danger">${escapeHtml(err.message)}</div>`;
    }
}

// ---------------------------------------------------------------------------
// Empirical Evaluation Suite (Experiments A-F)
// ---------------------------------------------------------------------------
let globalExperiments = [];

async function loadExperiments() {
    const container = document.getElementById("experimentsContainer");
    if (!container) return;

    try {
        const res = await fetch(`${API_BASE}/api/experiments/results`);
        if (!res.ok) throw new Error("Could not load experiments");
        const json = await res.json();
        globalExperiments = json.experiments || [];
        renderExperiments(globalExperiments);
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">Error loading experiments: ${escapeHtml(e.message)}</div>`;
    }
}

function filterExperiments(filterKey) {
    if (filterKey === "all") {
        renderExperiments(globalExperiments);
    } else {
        const targetId = `experiment_${filterKey}`;
        renderExperiments(globalExperiments.filter(e => e.id === targetId));
    }
}

function renderExperiments(exps) {
    const container = document.getElementById("experimentsContainer");
    if (!container) return;
    if (exps.length === 0) {
        container.innerHTML = `<div class="text-center py-4 text-muted">No experiment results found. Run python -m chaintrust.experiments to generate.</div>`;
        return;
    }

    container.innerHTML = exps.map(exp => {
        const tableHeaders = (exp.headers || []).map(h => `<th>${escapeHtml(h)}</th>`).join("");
        const tableRows = (exp.data || []).map(row => {
            const cells = (exp.headers || []).map(h => `<td>${escapeHtml(String(row[h] ?? ''))}</td>`).join("");
            return `<tr>${cells}</tr>`;
        }).join("");

        return `
            <div class="border border-secondary rounded-3 p-4 bg-dark bg-opacity-50 shadow-sm" id="card-${exp.id}">
                <div class="d-flex flex-column flex-md-row justify-content-between align-items-md-start gap-2 mb-3">
                    <div>
                        <h5 class="text-white fw-bold mb-1"><i class="fa-solid fa-chart-pie text-info me-2"></i>${escapeHtml(exp.name)}</h5>
                        <p class="text-secondary small mb-0">${escapeHtml(exp.description)}</p>
                    </div>
                    <div class="d-flex gap-2">
                        <a href="${exp.image_url}" target="_blank" class="btn btn-sm btn-outline-info text-nowrap"><i class="fa-solid fa-up-right-from-square me-1"></i>Open Chart</a>
                        <a href="${exp.csv_url}" download class="btn btn-sm btn-outline-secondary text-nowrap"><i class="fa-solid fa-download me-1"></i>CSV</a>
                    </div>
                </div>

                <div class="row g-4 align-items-center mb-3">
                    <div class="col-lg-7 text-center">
                        <div class="rounded-3 overflow-hidden border border-secondary bg-black p-2">
                            <img src="${exp.image_url}" alt="${escapeHtml(exp.name)}" class="img-fluid rounded" style="max-height: 420px; object-fit: contain;">
                        </div>
                    </div>
                    <div class="col-lg-5">
                        <div class="border border-secondary-subtle rounded-3 p-3 bg-dark bg-opacity-75">
                            <h6 class="text-white fw-bold mb-2 small"><i class="fa-solid fa-table me-2 text-warning"></i>Empirical Results Data</h6>
                            <div class="table-responsive" style="max-height: 380px; overflow-y: auto;">
                                <table class="table table-sm table-custom mb-0" style="font-size: 0.82rem;">
                                    <thead><tr>${tableHeaders}</tr></thead>
                                    <tbody>${tableRows}</tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join("");
}

// ---------------------------------------------------------------------------
// 6. Task Bank
// ---------------------------------------------------------------------------
async function loadTasks() {
    const tbody = document.getElementById("tasksBody");
    if (!tbody) return;

    try {
        const res = await fetch(`${API_BASE}/api/tasks?limit=50`);
        if (!res.ok) return;
        const tasks = await res.json();

        tbody.innerHTML = tasks.map(t => {
            const diff = t.difficulty_weight !== null ? t.difficulty_weight.toFixed(3) : "0.500";
            const diffColor = diff > 0.6 ? "text-danger" : (diff > 0.35 ? "text-warning" : "text-success");
            return `
                <tr>
                    <td class="fw-bold text-light">${escapeHtml(t.task_id)}</td>
                    <td><span class="badge bg-secondary">${escapeHtml(t.source)}</span></td>
                    <td><code class="text-info">${escapeHtml(t.entry_point || "function")}</code></td>
                    <td class="text-end fw-bold ${diffColor}">${diff}</td>
                </tr>
            `;
        }).join("");
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-center py-4 text-danger">Error loading tasks</td></tr>`;
    }
}

// ---------------------------------------------------------------------------
// 7. Web Audio Sci-Fi Synthesizer (Native Web Audio API)
// ---------------------------------------------------------------------------
let audioCtx = null;
let sfxEnabled = true;

function initAudioContext() {
    if (!audioCtx) {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (AudioContextClass) {
            audioCtx = new AudioContextClass();
        }
    }
    if (audioCtx && audioCtx.state === "suspended") {
        audioCtx.resume();
    }
}

function toggleSFX() {
    sfxEnabled = !sfxEnabled;
    const label = document.getElementById("sfxLabel");
    const btn = document.getElementById("btnToggleSFX");
    if (label) label.innerText = `SFX: ${sfxEnabled ? "ON" : "OFF"}`;
    if (btn) {
        btn.classList.toggle("btn-outline-info", sfxEnabled);
        btn.classList.toggle("btn-outline-secondary", !sfxEnabled);
    }
    if (sfxEnabled) {
        initAudioContext();
        playWarpSound();
    }
}

function playWarpSound() {
    if (!sfxEnabled) return;
    try {
        initAudioContext();
        if (!audioCtx) return;
        const now = audioCtx.currentTime;
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        const filter = audioCtx.createBiquadFilter();

        osc.type = "sawtooth";
        osc.frequency.setValueAtTime(140, now);
        osc.frequency.exponentialRampToValueAtTime(840, now + 0.45);
        osc.frequency.exponentialRampToValueAtTime(320, now + 0.9);

        filter.type = "lowpass";
        filter.frequency.setValueAtTime(300, now);
        filter.frequency.exponentialRampToValueAtTime(2800, now + 0.4);
        filter.frequency.exponentialRampToValueAtTime(600, now + 0.9);

        gain.gain.setValueAtTime(0.01, now);
        gain.gain.linearRampToValueAtTime(0.18, now + 0.3);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.95);

        osc.connect(filter);
        filter.connect(gain);
        gain.connect(audioCtx.destination);

        osc.start(now);
        osc.stop(now + 1.0);
    } catch (e) {}
}

function playTypeSound() {
    if (!sfxEnabled) return;
    try {
        if (!audioCtx) return;
        const now = audioCtx.currentTime;
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();

        osc.type = "triangle";
        osc.frequency.setValueAtTime(1200 + Math.random() * 400, now);

        gain.gain.setValueAtTime(0.02, now);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.04);

        osc.connect(gain);
        gain.connect(audioCtx.destination);

        osc.start(now);
        osc.stop(now + 0.045);
    } catch (e) {}
}

function playScanSound() {
    if (!sfxEnabled) return;
    try {
        initAudioContext();
        if (!audioCtx) return;
        const now = audioCtx.currentTime;
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();

        osc.type = "sine";
        osc.frequency.setValueAtTime(450, now);
        osc.frequency.linearRampToValueAtTime(1450, now + 0.28);

        gain.gain.setValueAtTime(0.01, now);
        gain.gain.linearRampToValueAtTime(0.12, now + 0.1);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);

        osc.connect(gain);
        gain.connect(audioCtx.destination);

        osc.start(now);
        osc.stop(now + 0.36);
    } catch (e) {}
}

function playSuccessSound() {
    if (!sfxEnabled) return;
    try {
        initAudioContext();
        if (!audioCtx) return;
        const now = audioCtx.currentTime;
        const notes = [523.25, 659.25, 783.99, 1046.50]; // C5, E5, G5, C6
        notes.forEach((freq, idx) => {
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            const start = now + idx * 0.09;

            osc.type = "sine";
            osc.frequency.setValueAtTime(freq, start);

            gain.gain.setValueAtTime(0.01, start);
            gain.gain.linearRampToValueAtTime(0.14, start + 0.03);
            gain.gain.exponentialRampToValueAtTime(0.001, start + 0.45);

            osc.connect(gain);
            gain.connect(audioCtx.destination);

            osc.start(start);
            osc.stop(start + 0.5);
        });
    } catch (e) {}
}

// ---------------------------------------------------------------------------
// 8. 3D Cyberspace Agent Holo-Chamber (Three.js WebGL Engine)
// ---------------------------------------------------------------------------
let chamberScene = null;
let chamberCamera = null;
let chamberRenderer = null;
let agentMeshGroup = null;
let agentCoreMesh = null;
let agentShellMesh = null;
let agentPointLight = null;
let agentRings = [];
let agentPods = [];
let agentPodLines = [];
let portalGroup = null;
let portalParticles = null;
let pedestalMesh = null;
let pedestalCrystal = null;
let dataBeamMesh = null;
let dataPulses = [];
let scannerPlane = null;
let merkleUplinkBeam = null;
let floorShockwaveMesh = null;

let isAutoOrbit = true;
let isChamberWorking = false;
let isChamberGrading = false;
let currentChamberState = "idle";
let currentAgent3D = null;

let cameraRadius = 26;
let cameraAngleX = 0.22;
let cameraAngleY = 0;

let warpAnim = {
    active: false,
    startTime: 0,
    duration: 1100,
    startY: 20,
    targetY: 0
};

function initAgent3DChamber() {
    const canvas = document.getElementById("agent-3d-canvas");
    if (!canvas || typeof THREE === "undefined" || chamberScene) return;

    chamberScene = new THREE.Scene();
    const wrapper = canvas.parentElement;
    const width = wrapper.clientWidth || 600;
    const height = wrapper.clientHeight || 380;

    chamberCamera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000);
    chamberCamera.position.set(0, 4, cameraRadius);

    chamberRenderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
    chamberRenderer.setSize(width, height);
    chamberRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    // Lights
    const ambientLight = new THREE.AmbientLight(0x1e293b, 1.2);
    chamberScene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.9);
    dirLight.position.set(10, 20, 15);
    chamberScene.add(dirLight);

    // Floor Cyber Grid
    const grid = new THREE.GridHelper(36, 36, 0x0ea5e9, 0x1e293b);
    grid.position.y = -6;
    chamberScene.add(grid);

    // Concentric Docking Pad on Floor
    const padGroup = new THREE.Group();
    padGroup.position.y = -5.9;
    const rGeo1 = new THREE.RingGeometry(5.2, 5.5, 48);
    const rMat1 = new THREE.MeshBasicMaterial({ color: 0x38bdf8, side: THREE.DoubleSide, transparent: true, opacity: 0.6 });
    const rMesh1 = new THREE.Mesh(rGeo1, rMat1);
    rMesh1.rotation.x = Math.PI / 2;
    padGroup.add(rMesh1);

    const rGeo2 = new THREE.RingGeometry(7.8, 8.0, 48);
    const rMat2 = new THREE.MeshBasicMaterial({ color: 0xa855f7, side: THREE.DoubleSide, transparent: true, opacity: 0.35 });
    const rMesh2 = new THREE.Mesh(rGeo2, rMat2);
    rMesh2.rotation.x = Math.PI / 2;
    padGroup.add(rMesh2);
    chamberScene.add(padGroup);

    // Floor Shockwave Ring
    const swGeo = new THREE.RingGeometry(0.2, 0.6, 48);
    const swMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8, side: THREE.DoubleSide, transparent: true, opacity: 0 });
    floorShockwaveMesh = new THREE.Mesh(swGeo, swMat);
    floorShockwaveMesh.rotation.x = Math.PI / 2;
    floorShockwaveMesh.position.y = -5.85;
    chamberScene.add(floorShockwaveMesh);

    // Overhead Warp Portal Gate
    portalGroup = new THREE.Group();
    portalGroup.position.set(0, 16, 0);

    const portalRingGeo = new THREE.TorusGeometry(6.2, 0.18, 16, 64);
    const portalRingMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.85 });
    const portalRing = new THREE.Mesh(portalRingGeo, portalRingMat);
    portalRing.rotation.x = Math.PI / 2;
    portalGroup.add(portalRing);

    // Portal Vortex Particles
    const pCount = 100;
    const pGeo = new THREE.BufferGeometry();
    const pPos = new Float32Array(pCount * 3);
    for (let i = 0; i < pCount; i++) {
        const rad = Math.random() * 5.8;
        const theta = Math.random() * Math.PI * 2;
        pPos[i * 3] = Math.cos(theta) * rad;
        pPos[i * 3 + 1] = (Math.random() - 0.5) * 2;
        pPos[i * 3 + 2] = Math.sin(theta) * rad;
    }
    pGeo.setAttribute("position", new THREE.BufferAttribute(pPos, 3));
    const pMat = new THREE.PointsMaterial({ color: 0x67e8f9, size: 0.3, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending });
    portalParticles = new THREE.Points(pGeo, pMat);
    portalGroup.add(portalParticles);
    chamberScene.add(portalGroup);

    // Compilation Pedestal (Data Receiver on the right)
    const pedGroup = new THREE.Group();
    pedGroup.position.set(7.5, -3.2, 1.5);

    const pedBaseGeo = new THREE.CylinderGeometry(1.6, 2.2, 5.6, 8);
    const pedBaseMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.4, metalness: 0.8, wireframe: true });
    const pedBase = new THREE.Mesh(pedBaseGeo, pedBaseMat);
    pedGroup.add(pedBase);

    const cGeo = new THREE.OctahedronGeometry(1.1);
    const cMat = new THREE.MeshStandardMaterial({ color: 0x38bdf8, emissive: 0x0284c7, roughness: 0.2, metalness: 0.9 });
    pedestalCrystal = new THREE.Mesh(cGeo, cMat);
    pedestalCrystal.position.y = 3.6;
    pedGroup.add(pedestalCrystal);
    pedestalMesh = pedGroup;
    chamberScene.add(pedGroup);

    // Data Laser Conduit (Connects agent core to pedestal)
    const beamCurve = new THREE.LineCurve3(new THREE.Vector3(0, 0, 0), new THREE.Vector3(7.5, 0.4, 1.5));
    const beamGeo = new THREE.TubeGeometry(beamCurve, 20, 0.08, 8, false);
    const beamMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.85, wireframe: true });
    dataBeamMesh = new THREE.Mesh(beamGeo, beamMat);
    dataBeamMesh.visible = false;
    chamberScene.add(dataBeamMesh);

    // Data Packet Pulses
    for (let i = 0; i < 4; i++) {
        const pulse = new THREE.Mesh(new THREE.SphereGeometry(0.2, 8, 8), new THREE.MeshBasicMaterial({ color: 0xffffff }));
        pulse.visible = false;
        chamberScene.add(pulse);
        dataPulses.push({ mesh: pulse, t: i * 0.25 });
    }

    // Scanning Laser Plane (Grading Sandbox)
    const scanGeo = new THREE.PlaneGeometry(16, 12);
    const scanMat = new THREE.MeshBasicMaterial({ color: 0x10b981, side: THREE.DoubleSide, transparent: true, opacity: 0.25, wireframe: true });
    scannerPlane = new THREE.Mesh(scanGeo, scanMat);
    scannerPlane.rotation.x = Math.PI / 2;
    scannerPlane.position.set(0, -1, 0);
    scannerPlane.visible = false;
    chamberScene.add(scannerPlane);

    // Merkle Blockchain Uplink Pillar
    const uplinkGeo = new THREE.CylinderGeometry(0.9, 0.9, 36, 16);
    const uplinkMat = new THREE.MeshBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.4, wireframe: true });
    merkleUplinkBeam = new THREE.Mesh(uplinkGeo, uplinkMat);
    merkleUplinkBeam.position.set(0, 10, 0);
    merkleUplinkBeam.visible = false;
    chamberScene.add(merkleUplinkBeam);

    // ==========================================
    // The 3D Cyber Agent Mesh Structure
    // ==========================================
    agentMeshGroup = new THREE.Group();
    agentMeshGroup.position.set(0, 0, 0);

    // Core Crystal Polyhedron
    const coreGeo = new THREE.IcosahedronGeometry(2.0, 0);
    const coreMat = new THREE.MeshStandardMaterial({
        color: 0x38bdf8,
        emissive: 0x0284c7,
        emissiveIntensity: 0.8,
        roughness: 0.2,
        metalness: 0.9,
    });
    agentCoreMesh = new THREE.Mesh(coreGeo, coreMat);
    agentMeshGroup.add(agentCoreMesh);

    // Exoskeleton Shell
    const shellGeo = new THREE.DodecahedronGeometry(2.7);
    const shellMat = new THREE.MeshBasicMaterial({
        color: 0x93c5fd,
        wireframe: true,
        transparent: true,
        opacity: 0.5
    });
    agentShellMesh = new THREE.Mesh(shellGeo, shellMat);
    agentMeshGroup.add(agentShellMesh);

    // Core Point Light
    agentPointLight = new THREE.PointLight(0x38bdf8, 2.4, 20);
    agentMeshGroup.add(agentPointLight);

    // Gyroscopic Tech Rings (3 Concentric Rings)
    agentRings = [];
    const ringConfigs = [
        { radius: 3.5, tube: 0.08, color: 0x38bdf8, rotAxis: "x" },
        { radius: 4.3, tube: 0.08, color: 0xa855f7, rotAxis: "y" },
        { radius: 5.1, tube: 0.06, color: 0x06b6d4, rotAxis: "z" },
    ];
    ringConfigs.forEach(cfg => {
        const rGeo = new THREE.TorusGeometry(cfg.radius, cfg.tube, 16, 64);
        const rMat = new THREE.MeshStandardMaterial({ color: cfg.color, emissive: cfg.color, emissiveIntensity: 0.4, roughness: 0.3, metalness: 0.8 });
        const rMesh = new THREE.Mesh(rGeo, rMat);
        agentMeshGroup.add(rMesh);
        agentRings.push({ mesh: rMesh, axis: cfg.rotAxis, speed: 0.015 });
    });

    // 4 Orbiting Satellite Sensor Pods
    agentPods = [];
    agentPodLines = [];
    const podGeo = new THREE.OctahedronGeometry(0.45);
    const podMat = new THREE.MeshStandardMaterial({ color: 0x38bdf8, emissive: 0x0284c7, roughness: 0.3 });
    const tetherLineMat = new THREE.LineBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.4 });

    for (let i = 0; i < 4; i++) {
        const podMesh = new THREE.Mesh(podGeo, podMat);
        agentMeshGroup.add(podMesh);
        agentPods.push({ mesh: podMesh, angle: (i * Math.PI) / 2, radius: 6.6, speed: 0.02 });

        const lGeo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), new THREE.Vector3(6.6, 0, 0)]);
        const line = new THREE.Line(lGeo, tetherLineMat);
        agentMeshGroup.add(line);
        agentPodLines.push(line);
    }

    chamberScene.add(agentMeshGroup);

    // Interactive Mouse Orbit & Zoom
    let isDragging = false;
    let prevMouseX = 0, prevMouseY = 0;
    canvas.addEventListener("mousedown", (e) => {
        isDragging = true;
        prevMouseX = e.clientX;
        prevMouseY = e.clientY;
        initAudioContext();
    });
    window.addEventListener("mouseup", () => isDragging = false);
    window.addEventListener("mousemove", (e) => {
        if (!isDragging) return;
        const deltaX = e.clientX - prevMouseX;
        const deltaY = e.clientY - prevMouseY;
        prevMouseX = e.clientX;
        prevMouseY = e.clientY;
        cameraAngleY -= deltaX * 0.007;
        cameraAngleX = Math.max(-0.35, Math.min(0.75, cameraAngleX + deltaY * 0.007));
        isAutoOrbit = false;
        const btnRot = document.getElementById("btn3dRotate");
        if (btnRot) btnRot.classList.remove("active");
    });
    canvas.addEventListener("wheel", (e) => {
        e.preventDefault();
        cameraRadius = Math.max(12, Math.min(44, cameraRadius + e.deltaY * 0.035));
    }, { passive: false });

    window.addEventListener("resize", resizeAgent3DChamber);

    animateAgentChamber();
}

function resizeAgent3DChamber() {
    const canvas = document.getElementById("agent-3d-canvas");
    if (!canvas || !chamberRenderer || !chamberCamera) return;
    const wrapper = canvas.parentElement;
    if (!wrapper) return;
    const w = wrapper.clientWidth || 600;
    const h = wrapper.clientHeight || 380;
    chamberCamera.aspect = w / h;
    chamberCamera.updateProjectionMatrix();
    chamberRenderer.setSize(w, h);
}

function animateAgentChamber() {
    requestAnimationFrame(animateAgentChamber);
    if (!chamberScene || !chamberCamera || !chamberRenderer) return;

    const time = performance.now() * 0.001;

    // Smooth Orbit Camera
    if (isAutoOrbit) {
        cameraAngleY += 0.0035;
    }
    chamberCamera.position.x = Math.sin(cameraAngleY) * Math.cos(cameraAngleX) * cameraRadius;
    chamberCamera.position.y = Math.sin(cameraAngleX) * cameraRadius + 3.0;
    chamberCamera.position.z = Math.cos(cameraAngleY) * Math.cos(cameraAngleX) * cameraRadius;
    chamberCamera.lookAt(0, 1.2, 0);

    // Warp Ingress Animation interpolation
    if (warpAnim.active) {
        const elapsed = performance.now() - warpAnim.startTime;
        const progress = Math.min(1.0, elapsed / warpAnim.duration);
        // Ease-out cubic with slight bounce
        const ease = 1 - Math.pow(1 - progress, 3);
        const currentY = warpAnim.startY + (warpAnim.targetY - warpAnim.startY) * ease;
        const currentScale = 0.02 + 0.98 * ease;

        if (agentMeshGroup) {
            agentMeshGroup.position.y = currentY;
            agentMeshGroup.scale.set(currentScale, currentScale, currentScale);
        }

        if (progress >= 1.0) {
            warpAnim.active = false;
            agentMeshGroup.position.y = 0;
            agentMeshGroup.scale.set(1, 1, 1);
            triggerFloorShockwave();
            const banner = document.getElementById("warpBanner");
            if (banner) banner.classList.add("d-none");
            const phaseBadge = document.getElementById("agent3dPhase");
            if (phaseBadge) {
                phaseBadge.innerText = "IDLE";
                phaseBadge.className = "badge bg-dark border border-success text-success ms-2";
            }
            const statusDot = document.getElementById("agent3dStatusDot");
            if (statusDot) statusDot.className = "status-dot status-dot-green";
            const spin = document.getElementById("telemetrySpin");
            if (spin) spin.innerText = "Stable 1,200 RPM";
        }
    } else if (agentMeshGroup) {
        // Normal breathing levitation
        agentMeshGroup.position.y = Math.sin(time * 1.5) * 0.35;
    }

    // Portal Ring & Vortex Animation
    if (portalGroup) {
        portalGroup.rotation.y += 0.015;
    }
    if (portalParticles) {
        portalParticles.rotation.y -= 0.03;
    }

    // Core & Shell Rotations
    if (agentCoreMesh) {
        agentCoreMesh.rotation.y += 0.01;
        agentCoreMesh.rotation.x += 0.007;
    }
    if (agentShellMesh) {
        agentShellMesh.rotation.y -= 0.008;
        agentShellMesh.rotation.z += 0.005;
    }

    // Gyro Rings Rotations (Accelerates in 'working' state)
    const ringMultiplier = isChamberWorking ? 4.5 : (isChamberGrading ? 2.5 : 1.0);
    agentRings.forEach((r, idx) => {
        if (r.axis === "x") r.mesh.rotation.x += r.speed * ringMultiplier;
        if (r.axis === "y") r.mesh.rotation.y += r.speed * ringMultiplier * 1.3;
        if (r.axis === "z") r.mesh.rotation.z += r.speed * ringMultiplier * 0.9;
    });

    // Orbiting Pods & Dynamic Laser Tethers
    agentPods.forEach((p, idx) => {
        p.angle += p.speed * (isChamberWorking ? 3.0 : 1.0);
        const px = Math.cos(p.angle) * p.radius;
        const pz = Math.sin(p.angle) * p.radius;
        const py = Math.sin(time * 2 + idx) * 1.2;
        p.mesh.position.set(px, py, pz);
        p.mesh.rotation.y += 0.03;

        // Update tether line
        const line = agentPodLines[idx];
        if (line) {
            const posAttr = line.geometry.attributes.position;
            posAttr.setXYZ(1, px, py, pz);
            posAttr.needsUpdate = true;
        }
    });

    // Compilation Pedestal crystal rotation
    if (pedestalCrystal) {
        pedestalCrystal.rotation.y += 0.02;
        pedestalCrystal.rotation.x += 0.01;
        pedestalCrystal.position.y = 3.6 + Math.sin(time * 2) * 0.2;
    }

    // Data Laser Pulses Animation along Conduit
    if (isChamberWorking && dataBeamMesh && dataBeamMesh.visible) {
        dataPulses.forEach(p => {
            p.mesh.visible = true;
            p.t = (p.t + 0.035) % 1.0;
            const startV = new THREE.Vector3(0, agentMeshGroup.position.y, 0);
            const targetV = new THREE.Vector3(7.5, 0.4, 1.5);
            p.mesh.position.lerpVectors(startV, targetV, p.t);
        });
    } else {
        dataPulses.forEach(p => p.mesh.visible = false);
    }

    // Scanner Plane sweep (Grading state)
    if (isChamberGrading && scannerPlane && scannerPlane.visible) {
        scannerPlane.position.y = -4 + Math.sin(time * 5) * 4;
    }

    // Floor Shockwave Animation
    if (floorShockwaveMesh && floorShockwaveMesh.material.opacity > 0.005) {
        floorShockwaveMesh.scale.x += 0.22;
        floorShockwaveMesh.scale.y += 0.22;
        floorShockwaveMesh.material.opacity *= 0.92;
    }

    chamberRenderer.render(chamberScene, chamberCamera);
}

function triggerFloorShockwave() {
    if (!floorShockwaveMesh) return;
    floorShockwaveMesh.scale.set(1, 1, 1);
    floorShockwaveMesh.material.opacity = 0.9;
}

function triggerAgentWarpEntrance(agent) {
    if (!agent) {
        agent = globalAgents[0];
        if (!agent) return;
    }
    currentAgent3D = agent;

    initAudioContext();
    playWarpSound();

    // Map theme colors
    let coreColor = 0x38bdf8;
    let emissiveColor = 0x0284c7;
    let dotClass = "status-dot-cyan";
    const prov = (agent.provider || "").toLowerCase();

    if (prov.includes("gemini")) {
        coreColor = 0x38bdf8;
        emissiveColor = 0x0284c7;
        dotClass = "status-dot-cyan";
    } else if (prov.includes("groq")) {
        coreColor = 0xf59e0b;
        emissiveColor = 0xd97706;
        dotClass = "status-dot-amber";
    } else if (prov.includes("openrouter") || prov.includes("anthropic")) {
        coreColor = 0xa855f7;
        emissiveColor = 0x7c3aed;
        dotClass = "status-dot-cyan";
    } else if (prov.includes("openai")) {
        coreColor = 0x10b981;
        emissiveColor = 0x059669;
        dotClass = "status-dot-green";
    }

    // Apply materials
    if (agentCoreMesh) {
        agentCoreMesh.material.color.setHex(coreColor);
        agentCoreMesh.material.emissive.setHex(emissiveColor);
    }
    if (agentPointLight) {
        agentPointLight.color.setHex(coreColor);
    }

    // Update HUD
    const nameEl = document.getElementById("agent3dName");
    if (nameEl) nameEl.innerText = agent.name;
    const phaseEl = document.getElementById("agent3dPhase");
    if (phaseEl) {
        phaseEl.innerText = "WARPING IN";
        phaseEl.className = "badge bg-warning text-dark fw-bold ms-2 animate-pulse";
    }
    const dotEl = document.getElementById("agent3dStatusDot");
    if (dotEl) dotEl.className = `status-dot ${dotClass}`;

    const provEl = document.getElementById("telemetryProvider");
    if (provEl) provEl.innerText = agent.provider;
    const stakeEl = document.getElementById("telemetryStake");
    if (stakeEl) stakeEl.innerText = `${agent.stake !== undefined ? agent.stake : 10} CT`;
    const spinEl = document.getElementById("telemetrySpin");
    if (spinEl) spinEl.innerText = "Ingress 4,800 RPM";

    // Show banner
    const banner = document.getElementById("warpBanner");
    const bannerText = document.getElementById("warpBannerText");
    if (banner && bannerText) {
        bannerText.innerText = `SYSTEM INGRESS: ${agent.name} WARPING IN`;
        banner.classList.remove("d-none");
    }

    // Sync quick cards
    document.querySelectorAll(".agent-pill-card").forEach(c => {
        c.classList.toggle("active", c.dataset.agentId === agent.agent_id);
    });

    // Start warp timeline
    warpAnim.active = true;
    warpAnim.startTime = performance.now();
    if (agentMeshGroup) {
        agentMeshGroup.position.set(0, warpAnim.startY, 0);
        agentMeshGroup.scale.set(0.02, 0.02, 0.02);
    }
}

function setChamberState(state) {
    currentChamberState = state;
    const phaseEl = document.getElementById("agent3dPhase");
    const spinEl = document.getElementById("telemetrySpin");
    const dotEl = document.getElementById("agent3dStatusDot");

    if (state === "working") {
        isChamberWorking = true;
        isChamberGrading = false;
        if (dataBeamMesh) dataBeamMesh.visible = true;
        if (scannerPlane) scannerPlane.visible = false;
        if (merkleUplinkBeam) merkleUplinkBeam.visible = false;

        if (phaseEl) {
            phaseEl.innerText = "NEURAL SYNTHESIS (WORKING)";
            phaseEl.className = "badge bg-warning text-dark fw-bold ms-2 animate-pulse";
        }
        if (spinEl) spinEl.innerText = "Overdrive 8,400 RPM";
        if (dotEl) dotEl.className = "status-dot status-dot-amber";

    } else if (state === "grading") {
        isChamberWorking = false;
        isChamberGrading = true;
        if (dataBeamMesh) dataBeamMesh.visible = false;
        if (scannerPlane) scannerPlane.visible = true;
        if (merkleUplinkBeam) merkleUplinkBeam.visible = false;

        playScanSound();

        if (phaseEl) {
            phaseEl.innerText = "ISOLATED GRADER (TESTING)";
            phaseEl.className = "badge bg-info text-dark fw-bold ms-2";
        }
        if (spinEl) spinEl.innerText = "Scanning 5,200 RPM";
        if (dotEl) dotEl.className = "status-dot status-dot-cyan";

    } else if (state === "verified") {
        isChamberWorking = false;
        isChamberGrading = false;
        if (dataBeamMesh) dataBeamMesh.visible = false;
        if (scannerPlane) scannerPlane.visible = false;
        if (merkleUplinkBeam) merkleUplinkBeam.visible = true;

        playSuccessSound();
        triggerFloorShockwave();

        if (phaseEl) {
            phaseEl.innerText = "VERIFIED & ANCHORED";
            phaseEl.className = "badge bg-success text-white fw-bold ms-2";
        }
        if (spinEl) spinEl.innerText = "Locked 1,200 RPM";
        if (dotEl) dotEl.className = "status-dot status-dot-green";

    } else {
        // IDLE
        isChamberWorking = false;
        isChamberGrading = false;
        if (dataBeamMesh) dataBeamMesh.visible = false;
        if (scannerPlane) scannerPlane.visible = false;
        if (merkleUplinkBeam) merkleUplinkBeam.visible = false;

        if (phaseEl) {
            phaseEl.innerText = "IDLE";
            phaseEl.className = "badge bg-dark border border-secondary text-secondary ms-2";
        }
        if (spinEl) spinEl.innerText = "Stable 1,200 RPM";
    }
}

function resetChamberCamera() {
    cameraRadius = 26;
    cameraAngleX = 0.22;
    cameraAngleY = 0;
    isAutoOrbit = true;
    const btn = document.getElementById("btn3dRotate");
    if (btn) btn.classList.add("active");
}

function focusChamberCore() {
    cameraRadius = 14;
    cameraAngleX = 0.08;
    isAutoOrbit = false;
    const btn = document.getElementById("btn3dRotate");
    if (btn) btn.classList.remove("active");
}

// ---------------------------------------------------------------------------
// 9. Interactive Quick Ingress Gallery
// ---------------------------------------------------------------------------
function populateAgentQuickRoster() {
    const container = document.getElementById("agentQuickRoster");
    if (!container || !globalAgents.length) return;

    container.innerHTML = globalAgents.map(ag => {
        let avatarClass = "avatar-gemini";
        let icon = '<i class="fa-solid fa-bolt"></i>';
        const prov = (ag.provider || "").toLowerCase();

        if (prov.includes("groq")) {
            avatarClass = "avatar-groq";
            icon = '<i class="fa-solid fa-microchip"></i>';
        } else if (prov.includes("openrouter") || prov.includes("anthropic")) {
            avatarClass = "avatar-openrouter";
            icon = '<i class="fa-solid fa-brain"></i>';
        } else if (prov.includes("openai")) {
            avatarClass = "avatar-openai";
            icon = '<i class="fa-solid fa-network-wired"></i>';
        }

        return `
            <div class="col-6 col-md-4 col-lg-2">
                <div class="agent-pill-card d-flex align-items-center gap-2" data-agent-id="${ag.agent_id}">
                    <div class="agent-pill-avatar ${avatarClass}">${icon}</div>
                    <div class="overflow-hidden">
                        <div class="fw-bold text-white text-truncate small">${escapeHtml(ag.name)}</div>
                        <div class="text-secondary text-truncate" style="font-size: 0.72rem;">${escapeHtml(ag.provider)} &bull; ${ag.stake || 10} CT</div>
                    </div>
                </div>
            </div>
        `;
    }).join("");

    // Wire clicks to summon into 3D chamber
    container.querySelectorAll(".agent-pill-card").forEach(card => {
        card.addEventListener("click", () => {
            const agentId = card.dataset.agentId;
            const ag = globalAgents.find(a => a.agent_id === agentId);
            if (!ag) return;

            const select = document.getElementById("arenaAgentSelect");
            if (select) select.value = agentId;

            triggerAgentWarpEntrance(ag);
        });
    });

    if (globalAgents.length > 0) {
        const firstCard = container.querySelector(`[data-agent-id="${globalAgents[0].agent_id}"]`);
        if (firstCard) firstCard.classList.add("active");
    }
}

// ---------------------------------------------------------------------------
// 10. Interactive Code Studio & Streaming Engine
// ---------------------------------------------------------------------------
let currentCodeText = "";
let currentCodeTokens = 0;
let currentCodeLatency = 0;
let streamingInterval = null;

function startCodeStreaming(codeText, tokens = 0, latency = 0) {
    currentCodeText = codeText;
    currentCodeTokens = tokens;
    currentCodeLatency = latency;

    // Switch tab to Code Studio
    const tabCodeBtn = document.getElementById("tab-code-btn");
    if (tabCodeBtn) tabCodeBtn.click();

    const codeEl = document.getElementById("codeSnippetCode");
    const cursor = document.getElementById("typingCursor");
    const linesEl = document.getElementById("codeLineCount");
    const latEl = document.getElementById("codeLatency");
    const tokenBadge = document.getElementById("codeTokenBadge");
    const astEl = document.getElementById("codeAstStatus");

    if (!codeEl) return;

    if (streamingInterval) {
        clearInterval(streamingInterval);
        streamingInterval = null;
    }

    const lines = codeText.split("\n");
    if (linesEl) linesEl.innerText = `${lines.length} lines`;
    if (latEl) latEl.innerText = `Latency: ${latency}ms`;
    if (astEl) astEl.innerText = `AST Valid: YES`;
    if (tokenBadge) {
        tokenBadge.classList.remove("d-none");
        tokenBadge.innerText = `${tokens || 140} tokens`;
    }

    codeEl.innerText = "";
    if (cursor) cursor.classList.remove("d-none");

    let lineIndex = 0;
    let accumulated = "";

    streamingInterval = setInterval(() => {
        if (lineIndex < lines.length) {
            accumulated += lines[lineIndex] + "\n";
            codeEl.innerText = accumulated;

            if (lineIndex % 4 === 0) {
                playTypeSound();
            }

            lineIndex++;
        } else {
            clearInterval(streamingInterval);
            streamingInterval = null;
            if (cursor) cursor.classList.add("d-none");

            // Syntax highlighting
            if (typeof Prism !== "undefined" && Prism.highlightElement) {
                Prism.highlightElement(codeEl);
            }
        }
    }, 28);
}

function renderCodeInstant(codeText) {
    if (streamingInterval) {
        clearInterval(streamingInterval);
        streamingInterval = null;
    }
    const codeEl = document.getElementById("codeSnippetCode");
    const cursor = document.getElementById("typingCursor");
    if (!codeEl) return;

    codeEl.innerText = codeText;
    if (cursor) cursor.classList.add("d-none");

    if (typeof Prism !== "undefined" && Prism.highlightElement) {
        Prism.highlightElement(codeEl);
    }
}

function renderTestCases(grade, testsString, entryPoint) {
    const container = document.getElementById("testCasesContainer");
    const passedSummary = document.getElementById("testSummaryPassed");
    const labelSummary = document.getElementById("testSummaryLabel");
    const scoreSummary = document.getElementById("testQualityScore");
    const runtimeSummary = document.getElementById("testRuntimeMs");

    if (passedSummary) passedSummary.innerText = `${grade.tests_passed} / ${grade.tests_total}`;
    if (labelSummary) {
        labelSummary.innerText = grade.passed ? "All Tests Passed" : "Partial / Failed";
        labelSummary.className = grade.passed ? "small text-success fw-bold" : "small text-danger fw-bold";
    }
    if (scoreSummary) {
        scoreSummary.innerText = grade.quality_score.toFixed(3);
        scoreSummary.className = grade.passed ? "text-success mb-0" : "text-danger mb-0";
    }
    if (runtimeSummary) runtimeSummary.innerText = `${grade.runtime_ms} ms`;

    if (!container) return;

    // Parse assertions or create rows
    const total = grade.tests_total || 3;
    const passed = grade.tests_passed || 0;
    const fnName = entryPoint || "solution";

    let rowsHtml = "";
    for (let i = 1; i <= total; i++) {
        const isPassed = i <= passed;
        const statusBadge = isPassed
            ? `<span class="badge bg-success"><i class="fa-solid fa-check me-1"></i>PASSED</span>`
            : `<span class="badge bg-danger"><i class="fa-solid fa-xmark me-1"></i>FAILED</span>`;
        const borderClass = isPassed ? "test-case-passed" : "test-case-failed";
        const simTime = (0.12 + (i * 0.05)).toFixed(2);

        rowsHtml += `
            <div class="test-case-item ${borderClass}">
                <div class="d-flex align-items-center gap-2">
                    <span class="badge bg-dark border border-secondary">Test #${i}</span>
                    <span class="text-white">${escapeHtml(fnName)}_assert_${i}()</span>
                </div>
                <div class="d-flex align-items-center gap-3">
                    <span class="text-secondary small font-monospace">${simTime}ms</span>
                    ${statusBadge}
                </div>
            </div>
        `;
    }

    if (grade.stderr) {
        rowsHtml += `
            <div class="p-2 rounded bg-danger bg-opacity-10 border border-danger small text-danger font-monospace mt-2">
                <i class="fa-solid fa-triangle-exclamation me-1"></i><strong>${escapeHtml(grade.error_type || "RuntimeError")}:</strong> ${escapeHtml(grade.stderr.substring(0, 180))}
            </div>
        `;
    }

    container.innerHTML = rowsHtml;
}

// ---------------------------------------------------------------------------
// 11. Live Execution Arena Selectors & Pipeline
// ---------------------------------------------------------------------------
async function initArenaSelectors() {
    const agentSelect = document.getElementById("arenaAgentSelect");
    const taskSelect = document.getElementById("arenaTaskSelect");
    if (!agentSelect || !taskSelect) return;

    try {
        const [agentsRes, tasksRes] = await Promise.all([
            fetch(`${API_BASE}/api/agents`),
            fetch(`${API_BASE}/api/tasks?limit=50`)
        ]);

        if (agentsRes.ok) {
            const agents = await agentsRes.json();
            globalAgents = agents;
            agentSelect.innerHTML = agents.map(a => `
                <option value="${a.agent_id}">${escapeHtml(a.name)} (${escapeHtml(a.provider)} / ${escapeHtml(a.model)})</option>
            `).join("");

            populateAgentQuickRoster();

            // Warp in the first agent initially
            if (agents.length > 0) {
                setTimeout(() => triggerAgentWarpEntrance(agents[0]), 300);
            }

            agentSelect.addEventListener("change", (e) => {
                const ag = globalAgents.find(a => a.agent_id === e.target.value);
                if (ag) triggerAgentWarpEntrance(ag);
            });
        }

        if (tasksRes.ok) {
            const tasks = await tasksRes.json();
            globalTasks = tasks;
            taskSelect.innerHTML = tasks.map(t => `
                <option value="${t.task_id}">${escapeHtml(t.task_id)} (${escapeHtml(t.entry_point || "code")})</option>
            `).join("");

            updateTaskPreview();
            taskSelect.addEventListener("change", updateTaskPreview);
        }

        const btnRun = document.getElementById("btnRunArenaLive");
        if (btnRun) {
            btnRun.addEventListener("click", runLiveArenaExecution);
        }
    } catch (e) {
        console.error("Error setting up arena selectors", e);
    }
}

function updateTaskPreview() {
    const taskSelect = document.getElementById("arenaTaskSelect");
    if (!taskSelect) return;
    const tid = taskSelect.value;
    const task = globalTasks.find(t => t.task_id === tid);
    if (!task) return;

    document.getElementById("arenaTaskEntry").innerText = task.entry_point || "N/A";
    const diff = task.difficulty_weight !== null ? task.difficulty_weight.toFixed(3) : "0.500";
    document.getElementById("arenaTaskDiff").innerText = diff;
    document.getElementById("arenaTaskSource").innerText = task.source || "BENCHMARK";

    // Populate Prompt & Workflow tab preview
    const taskIdBadge = document.getElementById("promptTaskIdBadge");
    const targetEntry = document.getElementById("promptTargetEntry");
    const taskHardness = document.getElementById("promptTaskHardness");
    const taskDocstring = document.getElementById("promptTaskDocstring");
    const fullPromptText = document.getElementById("promptFullPromptText");
    const standardCodeEl = document.getElementById("compareStandardCode");

    if (taskIdBadge) taskIdBadge.innerText = task.task_id;
    if (targetEntry) targetEntry.innerText = task.entry_point || "solution";
    if (taskHardness) taskHardness.innerText = diff;

    let docstring = "";
    if (task.prompt) {
        if (task.prompt.includes('"""')) {
            const parts = task.prompt.split('"""');
            if (parts.length >= 2) docstring = parts[1].trim();
        } else if (task.prompt.includes("'''")) {
            const parts = task.prompt.split("'''");
            if (parts.length >= 2) docstring = parts[1].trim();
        }
        if (!docstring) docstring = task.prompt.trim();
    }
    if (taskDocstring) taskDocstring.innerText = docstring || `Implement algorithmic solution for '${task.entry_point || "solution"}'.`;
    if (fullPromptText) fullPromptText.innerText = task.prompt || "No prompt specification provided.";

    if (standardCodeEl && task.reference_solution) {
        standardCodeEl.innerText = task.reference_solution;
        if (typeof Prism !== "undefined" && Prism.highlightElement) {
            Prism.highlightElement(standardCodeEl);
        }
    }
}

function setArenaStep(step) {
    const steps = ["stepPrompt", "stepGen", "stepGrade", "stepRank"];
    steps.forEach((s, idx) => {
        const el = document.getElementById(s);
        if (!el) return;
        if (idx < step) {
            el.className = "stepper-step p-2 rounded bg-success text-white small shadow-sm";
        } else if (idx === step) {
            el.className = "stepper-step p-2 rounded bg-warning text-dark fw-bold small shadow-sm animate-pulse";
        } else {
            el.className = "stepper-step p-2 rounded bg-dark border border-secondary text-secondary small";
        }
    });
}

async function runLiveArenaExecution() {
    const agentSelect = document.getElementById("arenaAgentSelect");
    const taskSelect = document.getElementById("arenaTaskSelect");
    const terminal = document.getElementById("arenaTerminal");
    const btnRun = document.getElementById("btnRunArenaLive");
    const statusBadge = document.getElementById("arenaStatusBadge");

    const agentId = agentSelect.value;
    const taskId = taskSelect.value;
    if (!agentId || !taskId) {
        showToast("Select both an agent and a task.", "warning");
        return;
    }

    const agent = globalAgents.find(a => a.agent_id === agentId);
    const task = globalTasks.find(t => t.task_id === taskId);

    btnRun.disabled = true;
    btnRun.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>Synthesizing & Grading...`;
    statusBadge.innerHTML = `<span class="badge bg-warning text-dark px-3 py-2"><i class="fa-solid fa-spinner fa-spin me-1"></i> RUNNING</span>`;

    terminal.innerHTML = "";
    const log = (msg, color = "text-light") => {
        const line = document.createElement("div");
        line.className = `py-1 ${color}`;
        line.innerHTML = msg;
        terminal.appendChild(line);
        terminal.scrollTop = terminal.scrollHeight;
    };

    log(`[${new Date().toLocaleTimeString()}] <span class="text-info">&gt; Initializing transparent dispatch:</span>`, "text-info");
    log(`  Agent: <strong class="text-white">${escapeHtml(agent?.name || agentId)}</strong> [Provider: ${escapeHtml(agent?.provider || "N/A")}]`);
    log(`  Target Task: <strong class="text-white">${escapeHtml(taskId)}</strong> (Difficulty $d_t = ${task?.difficulty_weight?.toFixed(3) || "0.500"})`);

    // STEP 1: Prompt
    setArenaStep(0);
    setChamberState("working");
    await new Promise(r => setTimeout(r, 350));

    log(`\n[STEP 1: DISPATCHING PROMPT] Sending task requirements to model...`, "text-warning");
    setArenaStep(1);

    try {
        const res = await fetch(`${API_BASE}/api/runner/execute-live`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ agent_id: agentId, task_id: taskId })
        });

        const data = await res.json();

        if (!res.ok || data.status === "failed") {
            log(`\n[ERROR]: ${escapeHtml(data.error || "Execution failed")}`, "text-danger");
            statusBadge.innerHTML = `<span class="badge bg-danger px-3 py-2">FAILED</span>`;
            setChamberState("idle");
            showToast("Agent execution failed: " + (data.error || ""), "danger");
            return;
        }

        // Populate Prompt & Workflow Trace Details
        const sysPromptEl = document.getElementById("promptSystemPromptText");
        const fullPromptEl = document.getElementById("promptFullPromptText");
        const tokensInEl = document.getElementById("traceTokensIn");
        const tokensOutEl = document.getElementById("traceTokensOut");
        const latencyEl = document.getElementById("traceLatency");

        if (sysPromptEl && data.system_prompt) sysPromptEl.innerText = data.system_prompt;
        if (fullPromptEl && data.prompt) fullPromptEl.innerText = data.prompt;
        if (tokensInEl) tokensInEl.innerText = `${data.tokens_in || 180} tokens`;
        if (tokensOutEl) tokensOutEl.innerText = `${data.tokens_out || 85} tokens`;
        if (latencyEl) latencyEl.innerText = `${(data.latency_ms / 1000).toFixed(2)}s`;

        // STEP 2: Display Generated Code in Code Studio
        log(`\n[STEP 2: CODE SYNTHESIZED] Model completed code in ${data.latency_ms}ms (${data.tokens_out || 0} tokens)`, "text-success");
        startCodeStreaming(data.extracted_code, data.tokens_out, data.latency_ms);

        // STEP 3: Grading
        setArenaStep(2);
        setChamberState("grading");
        log(`[STEP 3: SANDBOX TEST HARNESS] Executing code against hidden unit tests in Docker...`, "text-warning");
        await new Promise(r => setTimeout(r, 450));

        const grade = data.grade;
        renderTestCases(grade, task.tests, task.entry_point);

        if (grade.passed) {
            log(`  &check; ALL TESTS PASSED! (${grade.tests_passed}/${grade.tests_total}) - Quality Score: <span class="text-success fw-bold">1.000</span> (Runtime: ${grade.runtime_ms}ms)`, "text-success");
        } else {
            log(`  &cross; TESTS FAILED (${grade.tests_passed}/${grade.tests_total}) - Quality: <span class="text-danger fw-bold">${grade.quality_score.toFixed(3)}</span> - Error: ${escapeHtml(grade.error_type || "AssertionError")}`, "text-danger");
        }

        // STEP 4: CHS Primary Reputation & Cryptography
        setArenaStep(3);
        setChamberState("verified");

        const rep = data.reputation;
        const myCHS = rep?.scores?.chs !== undefined ? rep.scores.chs.toFixed(4) : (rep?.chs_score !== undefined ? rep.chs_score.toFixed(4) : (rep?.scores?.tracerank !== undefined ? rep.scores.tracerank.toFixed(4) : "N/A"));
        const rankPos = rep?.chs_rank || rep?.tracerank_rank || "N/A";

        log(`\n[STEP 4: CHS REPUTATION & PROOF COMMITMENT]`, "text-info");
        log(`  Official CHS Score: <strong class="text-warning fs-6">${myCHS}</strong>`);
        log(`  Global Rank Position: <span class="badge bg-primary">#${rankPos} of ${rep?.total_agents || 6}</span>`);

        // Populate Merkle Proof Tab
        document.getElementById("arenaOutputHash").innerText = data.cryptography.raw_output_sha256;
        document.getElementById("arenaMerkleLeaf").innerText = data.cryptography.merkle_leaf_hash;
        document.getElementById("proofTraceRank").innerText = myCHS;
        document.getElementById("proofRankPos").innerText = `#${rankPos} of ${rep?.total_agents || 6}`;

        // Populate Standard vs Agent & Critique Tab
        if (data.analysis) {
            const rightList = document.getElementById("critiqueRightList");
            const wrongList = document.getElementById("critiqueWrongList");
            const rightBadge = document.getElementById("critiqueRightBadge");
            const wrongBadge = document.getElementById("critiqueWrongBadge");
            const standardCode = document.getElementById("compareStandardCode");
            const agentCode = document.getElementById("compareAgentCode");
            const agentBadge = document.getElementById("compareAgentBadge");
            const agentStatus = document.getElementById("compareAgentStatus");
            const agentScore = document.getElementById("compareAgentScore");

            if (rightList && data.analysis.what_went_right) {
                rightList.innerHTML = data.analysis.what_went_right.map(item => `
                    <li class="d-flex align-items-start gap-2">
                        <i class="fa-solid fa-check text-success mt-1"></i>
                        <span>${escapeHtml(item)}</span>
                    </li>
                `).join("");
            }

            if (wrongList && data.analysis.what_went_wrong) {
                wrongList.innerHTML = data.analysis.what_went_wrong.map(item => `
                    <li class="d-flex align-items-start gap-2">
                        <i class="fa-solid fa-circle-exclamation text-warning mt-1"></i>
                        <span>${escapeHtml(item)}</span>
                    </li>
                `).join("");
            }

            if (rightBadge) {
                rightBadge.innerText = grade.passed ? "All Passed" : `${grade.tests_passed}/${grade.tests_total} Tests`;
            }
            if (wrongBadge) {
                if (grade.passed) {
                    wrongBadge.innerText = "Clean Run";
                    wrongBadge.className = "badge bg-success bg-opacity-25 text-success border border-success border-opacity-50";
                } else {
                    wrongBadge.innerText = `${grade.tests_total - grade.tests_passed} Issues`;
                    wrongBadge.className = "badge bg-danger bg-opacity-25 text-danger border border-danger border-opacity-50";
                }
            }

            if (standardCode) {
                standardCode.innerText = data.analysis.reference_standard || data.reference_solution || "# Standard reference solution";
                if (typeof Prism !== "undefined" && Prism.highlightElement) {
                    Prism.highlightElement(standardCode);
                }
            }

            if (agentCode) {
                agentCode.innerText = data.extracted_code || "// No code generated";
                if (typeof Prism !== "undefined" && Prism.highlightElement) {
                    Prism.highlightElement(agentCode);
                }
            }

            if (agentBadge) agentBadge.innerText = escapeHtml(data.agent_name || agent?.name || "Active Agent");
            if (agentScore) agentScore.innerText = `Score: ${grade.quality_score.toFixed(3)}`;
            if (agentStatus) {
                agentStatus.innerHTML = grade.passed
                    ? `<i class="fa-solid fa-circle-check text-success me-1"></i>Passed Benchmark`
                    : `<i class="fa-solid fa-triangle-exclamation text-warning me-1"></i>Partial Score (${grade.tests_passed}/${grade.tests_total})`;
            }
        }

        statusBadge.innerHTML = `<span class="badge bg-success px-3 py-2"><i class="fa-solid fa-check me-1"></i> VERIFIED & SCORED</span>`;
        showToast(`Task complete! CHS Score: ${myCHS} (Rank #${rankPos})`, "success");

        // Refresh Background Leaderboard & Overview
        await Promise.allSettled([
            loadLeaderboard(document.getElementById("selectMethod")?.value || "chs"),
            loadAlgorithmComparison(),
            fetchOverviewKPIs()
        ]);

    } catch (err) {
        log(`\n[NETWORK ERROR]: ${escapeHtml(err.message)}`, "text-danger");
        statusBadge.innerHTML = `<span class="badge bg-danger px-3 py-2">ERROR</span>`;
        setChamberState("idle");
    } finally {
        btnRun.disabled = false;
        btnRun.innerHTML = `<i class="fa-solid fa-play me-2"></i>Dispatch Agent & Verify Live`;
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function escapeHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function showToast(message, type = "info") {
    const toastElem = document.getElementById("appToast");
    const toastBody = document.getElementById("toastBody");
    if (!toastElem || !toastBody) return;

    toastBody.innerText = message;
    toastElem.className = `toast align-items-center text-bg-${type} border-0`;
    const toast = new bootstrap.Toast(toastElem, { delay: 3500 });
    toast.show();
}

