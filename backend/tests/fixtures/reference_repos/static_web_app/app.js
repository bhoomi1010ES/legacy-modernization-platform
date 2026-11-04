document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("action-btn");
  const log = document.getElementById("log-list");
  btn.addEventListener("click", () => {
    const li = document.createElement("li");
    li.textContent = `Verification tick at ${new Date().toISOString()}`;
    log.appendChild(li);
  });
});
