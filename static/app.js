const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const sendButton = chatForm.querySelector("button");
const locationStatus = document.getElementById("location-status");

let userLocation = null;

function addBotBubble(text) {
  const el = document.createElement("div");
  el.className = "bubble bot";
  el.textContent = text;
  chatLog.appendChild(el);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function addUserBubble(text) {
  const el = document.createElement("div");
  el.className = "bubble user";
  el.textContent = text;
  chatLog.appendChild(el);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function addPlaceCards(places) {
  const wrap = document.createElement("div");
  wrap.className = "places";

  for (const place of places) {
    const card = document.createElement("div");
    card.className = "place-card";

    const name = document.createElement("div");
    name.className = "name";
    name.textContent = place.name;

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `${place.category} · ${place.distance} away`;

    const links = document.createElement("div");
    links.className = "links";

    const navLink = document.createElement("a");
    navLink.href = place.maps_url;
    navLink.target = "_blank";
    navLink.rel = "noopener";
    navLink.textContent = "🗺️ Navigate";
    links.appendChild(navLink);

    if (place.instagram_url) {
      const igLink = document.createElement("a");
      igLink.href = place.instagram_url;
      igLink.target = "_blank";
      igLink.rel = "noopener";
      igLink.textContent = "📱 Instagram";
      links.appendChild(igLink);
    }

    card.append(name, meta, links);
    wrap.appendChild(card);
  }

  chatLog.appendChild(wrap);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function enableChat() {
  chatInput.disabled = false;
  sendButton.disabled = false;
  chatInput.focus();
}

function requestLocation() {
  if (!navigator.geolocation) {
    locationStatus.textContent = "Geolocation isn't supported in this browser - enter a manual location below.";
    showManualLocationForm();
    return;
  }

  navigator.geolocation.getCurrentPosition(
    (pos) => {
      userLocation = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      locationStatus.textContent = "Location set. Ask away!";
      enableChat();
    },
    () => {
      locationStatus.textContent = "Location permission denied - enter your coordinates manually.";
      showManualLocationForm();
    },
    { enableHighAccuracy: true, timeout: 10000 }
  );
}

function showManualLocationForm() {
  const wrap = document.createElement("div");
  wrap.className = "bubble bot";

  const label = document.createElement("div");
  label.textContent = "Paste your coordinates (lat, lon):";
  wrap.appendChild(label);

  const row = document.createElement("form");
  row.style.display = "flex";
  row.style.gap = "0.4rem";
  row.style.marginTop = "0.5rem";

  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "32.0809, 34.7806";
  input.style.flex = "1";

  const button = document.createElement("button");
  button.type = "submit";
  button.textContent = "Set";

  row.append(input, button);
  wrap.appendChild(row);
  chatLog.appendChild(wrap);

  row.addEventListener("submit", (e) => {
    e.preventDefault();
    const parts = input.value.split(",").map((s) => parseFloat(s.trim()));
    if (parts.length !== 2 || parts.some(Number.isNaN)) {
      addBotBubble("That doesn't look like 'lat, lon' - try again.");
      return;
    }
    userLocation = { lat: parts[0], lon: parts[1] };
    locationStatus.textContent = "Location set. Ask away!";
    enableChat();
  });
}

async function sendMessage(message) {
  addUserBubble(message);

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, lat: userLocation.lat, lon: userLocation.lon }),
    });

    if (!res.ok) {
      addBotBubble("Something went wrong on the server. Try again in a moment.");
      return;
    }

    const data = await res.json();
    addBotBubble(data.reply);
    if (data.places && data.places.length) {
      addPlaceCards(data.places);
    }
  } catch (err) {
    addBotBubble("Couldn't reach the server - check your connection.");
  }
}

chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const message = chatInput.value.trim();
  if (!message || !userLocation) return;
  chatInput.value = "";
  sendMessage(message);
});

addBotBubble("Hi! I'll find the closest spot from your Tel Aviv food map once I know where you are.");
requestLocation();
