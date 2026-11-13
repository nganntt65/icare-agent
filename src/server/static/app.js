// iCare Client-Side Interaction Controller
document.addEventListener("DOMContentLoaded", () => {
  const sessionId = "student_session_" + Math.random().toString(36).substring(2, 9);
  const chatMessages = document.getElementById("chat-messages");
  const chatForm = document.getElementById("chat-form");
  const userInput = document.getElementById("user-input");
  const btnForget = document.getElementById("btn-forget");
  const presetButtons = document.querySelectorAll(".preset-btn");

  // Inspector Elements
  const inspectorSession = document.getElementById("inspector-session");
  const inspectorFsm = document.getElementById("inspector-fsm");
  const inspectorLang = document.getElementById("inspector-lang");
  const inspectorConfidence = document.getElementById("inspector-confidence");
  const inspectorPii = document.getElementById("inspector-pii");
  const inspectorCitations = document.getElementById("inspector-citations");
  const inspectorAudit = document.getElementById("inspector-audit");
  const systemStatus = document.getElementById("system-status");

  inspectorSession.textContent = sessionId;

  // 1. Health check on start
  fetch("/api/health")
    .then(res => res.json())
    .then(data => {
      systemStatus.textContent = `Online (${data.total_indexed_chunks} chunks)`;
    })
    .catch(() => {
      systemStatus.textContent = "Offline";
    });

  // Simple markdown renderer for chat bubbles
  function renderMarkdown(text) {
    if (!text) return "";
    let html = text
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") // escape
      .replace(/^### (.*$)/gim, '<h3>$1</h3>')
      .replace(/^## (.*$)/gim, '<h2>$1</h2>')
      .replace(/^# (.*$)/gim, '<h1>$1</h1>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/\n\n/g, '<p></p>')
      .replace(/\n- (.*)/g, '<li>$1</li>');
    
    // Wrap consecutive li in ul
    html = html.replace(/(<li>.*?<\/li>)+/g, '<ul>$&</ul>');
    html = html.replace(/\n/g, '<br/>');
    return html;
  }

  // Append a message to the chat window
  function appendMessage(role, content, lang = null) {
    const msgDiv = document.createElement("div");
    msgDiv.className = `message ${role}`;

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = role === "user" ? "👤" : "🤖";

    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";

    if (role === "assistant") {
      const header = document.createElement("div");
      header.className = "message-header";
      header.innerHTML = `
        <span class="sender-name">iCare Navigator</span>
        <span class="lang-tag">${lang ? lang.toUpperCase() : "VERIFIED"}</span>
      `;
      contentDiv.appendChild(header);
    }

    const bodyDiv = document.createElement("div");
    bodyDiv.innerHTML = renderMarkdown(content);
    contentDiv.appendChild(bodyDiv);

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(contentDiv);
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  // Update Inspector Sidebar with response state
  function updateInspector(data) {
    // FSM State badge
    inspectorFsm.textContent = data.fsm_state;
    inspectorFsm.className = "fsm-status-badge";
    if (data.is_crisis) {
      inspectorFsm.classList.add("state-crisis");
    } else if (data.is_injection) {
      inspectorFsm.classList.add("state-security");
    } else {
      inspectorFsm.classList.add("state-completed");
    }

    inspectorLang.textContent = (data.detected_lang || "en").toUpperCase();
    inspectorConfidence.textContent = data.confidence_score ? data.confidence_score.toFixed(2) : "N/A";

    // PII Redactions
    if (data.redactions && data.redactions.length > 0) {
      const items = data.redactions.map(r => `<div>🔒 <strong>${r.type}</strong>: <code>${r.original_masked}</code></div>`).join("");
      inspectorPii.innerHTML = items;
    } else {
      inspectorPii.innerHTML = '<span class="empty-state">No sensitive personal identifiers detected.</span>';
    }

    // Citations
    if (data.citations && data.citations.length > 0) {
      inspectorCitations.innerHTML = data.citations.map(c => `
        <div class="citation-card">
          <div class="citation-source">📄 ${c.doc_title}</div>
          <div class="citation-section">§ ${c.section_title}</div>
          <div class="citation-snippet">"${c.snippet}"</div>
          <div class="citation-score">RRF Relevance Score: ${c.rrf_score.toFixed(4)}</div>
        </div>
      `).join("");
    } else {
      inspectorCitations.innerHTML = '<div class="empty-state">No verified citations attached.</div>';
    }

    // Audit Trace
    if (data.audit_trace && data.audit_trace.length > 0) {
      inspectorAudit.innerHTML = data.audit_trace.map(item => `
        <div class="audit-item">✓ ${item}</div>
      `).join("");
      inspectorAudit.scrollTop = inspectorAudit.scrollHeight;
    }
  }

  // Typing indicator functions
  function showTypingIndicator() {
    const id = "typing-indicator-msg";
    if (document.getElementById(id)) return;
    const msgDiv = document.createElement("div");
    msgDiv.id = id;
    msgDiv.className = "message assistant";
    msgDiv.innerHTML = `
      <div class="message-avatar">🤖</div>
      <div class="message-content" style="display:inline-flex; align-items:center; gap:8px;">
        <span style="font-size:12px; color:var(--text-muted);">Consulting verified campus regulations...</span>
        <div class="typing-indicator">
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
        </div>
      </div>
    `;
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function hideTypingIndicator() {
    const el = document.getElementById("typing-indicator-msg");
    if (el) el.remove();
  }

  // Render Action Proposal Interactive Card
  function appendActionProposal(proposal) {
    if (!proposal) return;
    const p = proposal.parameters || {};
    let paramsHtml = "";
    if (p.department) {
      paramsHtml += `<div class="action-param-row"><span class="action-param-key">Department:</span><span class="action-param-val">${p.department}</span></div>`;
    }
    if (p.location) {
      paramsHtml += `<div class="action-param-row"><span class="action-param-key">Location:</span><span class="action-param-val">${p.location}</span></div>`;
    }
    if (p.start_time || p.appointment_time) {
      const timeVal = (p.appointment_time || p.start_time || "").replace("T", " ").substring(0, 16);
      paramsHtml += `<div class="action-param-row"><span class="action-param-key">Schedule:</span><span class="action-param-val">${timeVal}</span></div>`;
    }

    const cardDiv = document.createElement("div");
    cardDiv.className = "action-card";
    cardDiv.innerHTML = `
      <div class="action-card-header">
        <span>📋 Two-Phase Commit Proposal</span>
        <span style="font-size:10px; background:rgba(255,255,255,0.2); padding:2px 6px; border-radius:4px;">${proposal.proposal_id}</span>
      </div>
      <div class="action-card-body">
        <div class="action-card-title">${proposal.title}</div>
        <div style="font-size:12px; color:var(--text-muted); margin-bottom:6px;">${proposal.description}</div>
        ${paramsHtml ? `<div class="action-card-params">${paramsHtml}</div>` : ""}
        <div class="action-card-safety">
          🔒 <strong>Taiwan PDPA Human Gate</strong>: Zero mutations allowed without your consent.
        </div>
        <div class="action-card-actions" id="actions-${proposal.proposal_id}">
          <button class="btn-confirm" id="btn-conf-${proposal.proposal_id}">✅ Confirm & Schedule</button>
          <button class="btn-cancel" id="btn-canc-${proposal.proposal_id}">❌ Cancel</button>
        </div>
      </div>
    `;

    const lastMsg = chatMessages.querySelector(".message.assistant:last-child .message-content");
    if (lastMsg) {
      lastMsg.appendChild(cardDiv);
    } else {
      const wrapper = document.createElement("div");
      wrapper.className = "message assistant";
      wrapper.appendChild(cardDiv);
      chatMessages.appendChild(wrapper);
    }
    chatMessages.scrollTop = chatMessages.scrollHeight;

    const btnConf = document.getElementById(`btn-conf-${proposal.proposal_id}`);
    const btnCanc = document.getElementById(`btn-canc-${proposal.proposal_id}`);
    const actionContainer = document.getElementById(`actions-${proposal.proposal_id}`);

    if (btnConf) {
      btnConf.addEventListener("click", async () => {
        btnConf.disabled = true;
        btnCanc.disabled = true;
        btnConf.textContent = "Executing...";

        try {
          const res = await fetch("/api/action/confirm", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              session_id: sessionId,
              proposal_id: proposal.proposal_id,
              token: proposal.confirmation_token
            })
          });
          const resultData = await res.json();
          if (resultData.success) {
            actionContainer.innerHTML = `<div style="color:var(--success); font-weight:700; font-size:12px; padding:6px 0;">✅ Confirmed & Executed under Two-Phase Gate</div>`;
            appendReceiptCard(resultData.receipt);
            inspectorFsm.textContent = "ACTION_EXECUTED";
            inspectorFsm.className = "fsm-status-badge state-completed";
          } else {
            actionContainer.innerHTML = `<div style="color:var(--danger); font-size:12px;">⚠️ Execution failed: ${resultData.error}</div>`;
          }
        } catch (e) {
          actionContainer.innerHTML = `<div style="color:var(--danger); font-size:12px;">⚠️ Network error: ${e.message}</div>`;
        }
      });
    }

    if (btnCanc) {
      btnCanc.addEventListener("click", async () => {
        btnConf.disabled = true;
        btnCanc.disabled = true;
        btnCanc.textContent = "Cancelling...";

        try {
          const res = await fetch("/api/action/cancel", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              session_id: sessionId,
              proposal_id: proposal.proposal_id
            })
          });
          actionContainer.innerHTML = `<div style="color:var(--text-muted); font-size:12px; padding:6px 0;">❌ Action Cancelled (Session state rolled back cleanly)</div>`;
          inspectorFsm.textContent = "COMPLETED";
          inspectorFsm.className = "fsm-status-badge state-completed";
        } catch (e) {
          actionContainer.innerHTML = `<div style="color:var(--danger); font-size:12px;">⚠️ Cancel error: ${e.message}</div>`;
        }
      });
    }
  }

  // Render Official Alphanumeric Receipt Card (REC-SCH-XXXX)
  function appendReceiptCard(receipt) {
    if (!receipt) return;
    const recDiv = document.createElement("div");
    recDiv.className = "receipt-card";
    const extRef = receipt.external_reference || "";
    const isLink = extRef.startsWith("http");

    recDiv.innerHTML = `
      <div class="receipt-card-header">
        <span>📜 Official Execution Receipt</span>
        <span style="font-family:monospace; font-size:11px;">${receipt.receipt_id}</span>
      </div>
      <div class="receipt-card-body">
        <div class="receipt-row">
          <span class="receipt-key">Status:</span>
          <span class="receipt-val">CONFIRMED & EXECUTED</span>
        </div>
        <div class="receipt-row">
          <span class="receipt-key">Action:</span>
          <span class="receipt-val">${receipt.title}</span>
        </div>
        <div class="receipt-row">
          <span class="receipt-key">Timestamp:</span>
          <span style="color:#0f172a; font-size:11px;">${(receipt.timestamp || "").replace("T", " ").substring(0, 19)} UTC</span>
        </div>
        <div class="receipt-row">
          <span class="receipt-key">Consent Proof:</span>
          <span style="font-family:monospace; font-size:11px; color:#475569;">${receipt.consent_verification_hash}</span>
        </div>
        ${isLink ? `<a href="${extRef}" target="_blank" class="btn-receipt-link">📅 View / Add in Google Calendar</a>` : (extRef ? `<div class="receipt-row"><span class="receipt-key">Reference Ticket:</span><span style="font-weight:700;">${extRef}</span></div>` : "")}
      </div>
    `;

    const lastMsg = chatMessages.querySelector(".message.assistant:last-child .message-content");
    if (lastMsg) {
      lastMsg.appendChild(recDiv);
    } else {
      const wrapper = document.createElement("div");
      wrapper.className = "message assistant";
      wrapper.appendChild(recDiv);
      chatMessages.appendChild(wrapper);
    }
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  // Send message API call
  async function sendMessage(text) {
    if (!text.trim()) return;

    appendMessage("user", text);
    userInput.value = "";
    userInput.disabled = true;
    const submitBtn = chatForm.querySelector("button[type='submit']");
    if (submitBtn) submitBtn.disabled = true;
    showTypingIndicator();

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: text })
      });

      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }

      const data = await response.json();
      hideTypingIndicator();
      appendMessage("assistant", data.answer, data.detected_lang);
      if (data.pending_action) {
        appendActionProposal(data.pending_action);
      }
      if (data.execution_receipt) {
        appendReceiptCard(data.execution_receipt);
      }
      updateInspector(data);
    } catch (err) {
      hideTypingIndicator();
      appendMessage("assistant", `⚠️ Connection error: ${err.message}. Please check if the server is running.`);
    } finally {
      userInput.disabled = false;
      if (submitBtn) submitBtn.disabled = false;
      userInput.focus();
    }
  }

  // Handle Form Submit
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(userInput.value);
  });

  // Handle Preset Scenario Buttons
  presetButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const query = btn.getAttribute("data-query");
      sendMessage(query);
    });
  });

  // Handle Memory Purge Button
  btnForget.addEventListener("click", async () => {
    sendMessage("/forget");
  });
});
