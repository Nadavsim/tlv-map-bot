const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const sendButton = chatForm.querySelector("button");
const locationStatus = document.getElementById("location-status");
const modeButtons = document.querySelectorAll("#mode-toggle button");

let userLocation = null;
let transportMode = "walking";

modeButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    transportMode = btn.dataset.mode;
    modeButtons.forEach((b) => b.classList.toggle("active", b === btn));
  });
});

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

    const categoryChip = document.createElement("span");
    categoryChip.className = "category-chip";
    categoryChip.textContent = place.category;

    const distanceEta = document.createElement("span");
    distanceEta.className = "distance-eta";
    distanceEta.textContent = place.eta ? `${place.distance} · ${place.eta}` : place.distance;

    meta.append(categoryChip, distanceEta);

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
  label.textContent =
    "Paste your coordinates, or a Google Maps link (tap-and-hold your spot in Maps → Share):";
  wrap.appendChild(label);

  const row = document.createElement("form");
  row.style.display = "flex";
  row.style.gap = "0.4rem";
  row.style.marginTop = "0.5rem";

  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "32.0809, 34.7806 or a maps.app.goo.gl link";
  input.style.flex = "1";

  const button = document.createElement("button");
  button.type = "submit";
  button.textContent = "Set";

  row.append(input, button);
  wrap.appendChild(row);
  chatLog.appendChild(wrap);

  row.addEventListener("submit", async (e) => {
    e.preventDefault();
    const value = input.value.trim();

    const parts = value.split(",").map((s) => parseFloat(s.trim()));
    if (parts.length === 2 && !parts.some(Number.isNaN)) {
      userLocation = { lat: parts[0], lon: parts[1] };
      locationStatus.textContent = "Location set. Ask away!";
      enableChat();
      return;
    }

    if (!value.includes("http://") && !value.includes("https://")) {
      addBotBubble("That doesn't look like 'lat, lon' or a Maps link - try again.");
      return;
    }

    button.disabled = true;
    button.textContent = "...";
    try {
      const res = await fetch("/api/resolve-location", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: value }),
      });
      const data = await res.json();
      if (data.lat == null || data.lon == null) {
        addBotBubble("Couldn't find coordinates in that link - try pasting the coordinates directly instead.");
        button.disabled = false;
        button.textContent = "Set";
        return;
      }
      userLocation = { lat: data.lat, lon: data.lon };
      locationStatus.textContent = "Location set. Ask away!";
      enableChat();
    } catch (err) {
      addBotBubble("Couldn't reach the server to resolve that link - try again.");
      button.disabled = false;
      button.textContent = "Set";
    }
  });
}

async function sendMessage(message) {
  addUserBubble(message);

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        lat: userLocation.lat,
        lon: userLocation.lon,
        mode: transportMode,
      }),
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
