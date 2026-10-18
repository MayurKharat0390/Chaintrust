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
        loadLeaderboard("tracerank"),
        loadAlgorithmComparison(),
        loadSybilResilience(),
        loadAnchors(),
        loadTasks(),
        loadBundleList()
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
                    await loadLeaderboard(document.getElementById("selectMethod")?.value || "tracerank");
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
async function loadLeaderboard(method = "tracerank") {
    const tbody = document.getElementById("leaderboardBody");
    if (!tbody) return;

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
            const providerClass = `badge-${item.provider.toLowerCase()}`;
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
    const methods = ["tracerank", "eigentrust", "pagerank", "simple_avg"];
    const colors = {
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
    const select = document.getElementById("selectBundle");
    const filename = select ? select.value : "";
    const resultsContainer = document.getElementById("verifyResults");

    if (!filename) {
        showToast("Please select a valid bundle.", "warning");
        return;
    }

    resultsContainer.innerHTML = `<div class="text-center py-4 text-info"><span class="spinner-border spinner-border-sm me-2"></span>Performing cryptographic verification & score recomputation...</div>`;

    try {
        const bundleRes = await fetch(`${API_BASE}/api/bundles/${filename}`);
        if (!bundleRes.ok) throw new Error("Could not fetch bundle content");
        const bundleData = await bundleRes.json();

        const checkOnChain = document.getElementById("checkOnChain")?.checked || false;

        const verifyRes = await fetch(`${API_BASE}/api/verify`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ bundle: bundleData, check_on_chain: checkOnChain })
        });

        if (!verifyRes.ok) throw new Error("Verification API failed");
        const res = await verifyRes.json();

        const statusBadge = (val) => val === true ? `<span class="badge-pass"><i class="fa-solid fa-check me-1"></i>PASS</span>` : (val === false ? `<span class="badge-fail"><i class="fa-solid fa-xmark me-1"></i>FAIL</span>` : `<span class="badge bg-secondary">SKIPPED</span>`);

        resultsContainer.innerHTML = `
            <div class="alert ${res.valid ? 'alert-success bg-opacity-10 border-success' : 'alert-danger bg-opacity-10 border-danger'} mb-3">
                <h5 class="fw-bold mb-1">${res.valid ? '✅ AUDIT VERIFICATION PASSED' : '❌ AUDIT VERIFICATION FAILED'}</h5>
                <div class="small">${res.valid ? 'The audit bundle is mathematically and cryptographically authentic!' : 'Tampering or calculation mismatch detected.'}</div>
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
            <div class="verify-item">
                <span>4. Mathematical Score Recomputation (${res.claimed_score.toFixed(4)} vs ${res.recomputed_score.toFixed(4)})</span>
                ${statusBadge(res.score_recomputed_valid)}
            </div>
            <div class="verify-item">
                <span>5. Score Commitment Hash</span>
                ${statusBadge(res.score_hash_valid)}
            </div>
            ${checkOnChain ? `
            <div class="verify-item">
                <span>6. On-Chain Anchor Commitment</span>
                ${statusBadge(res.on_chain_valid)}
            </div>` : ''}
        `;

    } catch (err) {
        resultsContainer.innerHTML = `<div class="alert alert-danger">${escapeHtml(err.message)}</div>`;
    }
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
// 7. Live Execution Arena & Telemetry Terminal
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

        // Run Live Execution Button
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
}

function setArenaStep(step) {
    const steps = ["stepPrompt", "stepGen", "stepGrade", "stepRank"];
    steps.forEach((s, idx) => {
        const el = document.getElementById(s);
        if (!el) return;
        if (idx < step) {
            el.className = "p-2 rounded bg-success text-white small shadow-sm";
        } else if (idx === step) {
            el.className = "p-2 rounded bg-warning text-dark fw-bold small shadow-sm animate-pulse";
        } else {
            el.className = "p-2 rounded bg-dark border border-secondary text-secondary small";
        }
    });
}

async function runLiveArenaExecution() {
    const agentSelect = document.getElementById("arenaAgentSelect");
    const taskSelect = document.getElementById("arenaTaskSelect");
    const terminal = document.getElementById("arenaTerminal");
    const btnRun = document.getElementById("btnRunArenaLive");
    const statusBadge = document.getElementById("arenaStatusBadge");
    const proofBox = document.getElementById("arenaProofBox");

    const agentId = agentSelect.value;
    const taskId = taskSelect.value;
    if (!agentId || !taskId) {
        showToast("Select both an agent and a task.", "warning");
        return;
    }

    const agent = globalAgents.find(a => a.agent_id === agentId);
    const task = globalTasks.find(t => t.task_id === taskId);

    btnRun.disabled = true;
    btnRun.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>Executing Live...`;
    statusBadge.innerHTML = `<span class="badge bg-warning text-dark px-3 py-2"><i class="fa-solid fa-spinner fa-spin me-1"></i> RUNNING</span>`;
    proofBox.classList.add("d-none");

    // Clear and start terminal stream
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

    setArenaStep(0);
    await new Promise(r => setTimeout(r, 400));

    log(`\n[STEP 1: DISPATCHING PROMPT] Sending task requirements to LLM...`, "text-warning");
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
            showToast("Agent execution failed: " + (data.error || ""), "danger");
            return;
        }

        // STEP 2: Display Generated Code
        log(`\n[STEP 2: CODE RECEIVED] Model returned response in ${data.latency_ms}ms (${data.tokens_out || 0} tokens)`, "text-success");
        log(`<div class="p-2 my-2 rounded bg-dark border border-secondary text-info"><pre class="mb-0 text-white" style="font-size: 0.8rem; white-space: pre-wrap;">${escapeHtml(data.extracted_code)}</pre></div>`);

        // STEP 3: Grading
        setArenaStep(2);
        log(`[STEP 3: SANDBOX TEST HARNESS] Executing code against unit tests...`, "text-warning");
        await new Promise(r => setTimeout(r, 400));

        const grade = data.grade;
        if (grade.passed) {
            log(`  &check; ALL TESTS PASSED! (${grade.tests_passed}/${grade.tests_total}) - Quality Score: <span class="text-success fw-bold">1.000</span> (Runtime: ${grade.runtime_ms}ms)`, "text-success");
        } else {
            log(`  &cross; TESTS FAILED (${grade.tests_passed}/${grade.tests_total}) - Quality: <span class="text-danger fw-bold">${grade.quality_score.toFixed(3)}</span> - Error: ${escapeHtml(grade.error_type || "AssertionError")}`, "text-danger");
            if (grade.stderr) {
                log(`  <span class="text-secondary small">${escapeHtml(grade.stderr.substring(0, 150))}</span>`, "text-danger");
            }
        }

        // STEP 4: TraceRank & Cryptography
        setArenaStep(3);
        const rep = data.reputation;
        const myTraceRank = rep?.scores?.tracerank !== undefined ? rep.scores.tracerank.toFixed(4) : "N/A";
        const rankPos = rep?.tracerank_rank || "N/A";

        log(`\n[STEP 4: TRACERANK & PROOF COMMITMENT]`, "text-info");
        log(`  Updated TraceRank Score: <strong class="text-warning fs-6">${myTraceRank}</strong>`);
        log(`  Global Rank Position: <span class="badge bg-primary">#${rankPos} of ${rep?.total_agents || 6}</span>`);

        // Show Proof Box
        proofBox.classList.remove("d-none");
        document.getElementById("arenaOutputHash").innerText = data.cryptography.raw_output_sha256;
        document.getElementById("arenaMerkleLeaf").innerText = data.cryptography.merkle_leaf_hash;

        statusBadge.innerHTML = `<span class="badge bg-success px-3 py-2"><i class="fa-solid fa-check me-1"></i> VERIFIED & SCORED</span>`;
        showToast(`Task complete! TraceRank: ${myTraceRank} (Rank #${rankPos})`, "success");

        // Refresh Background Leaderboard & Overview
        await Promise.allSettled([
            loadLeaderboard(document.getElementById("selectMethod")?.value || "tracerank"),
            loadAlgorithmComparison(),
            fetchOverviewKPIs()
        ]);

    } catch (err) {
        log(`\n[NETWORK ERROR]: ${escapeHtml(err.message)}`, "text-danger");
        statusBadge.innerHTML = `<span class="badge bg-danger px-3 py-2">ERROR</span>`;
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

// Ensure initArenaSelectors is called on DOM load
document.addEventListener("DOMContentLoaded", () => {
    initArenaSelectors();
});

