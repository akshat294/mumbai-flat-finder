const API_URL = "https" + "://bombayhomes.pages.dev/api/listings";
const $ = id => document.getElementById(id);
let currentUrl = "";

chrome.tabs.query({ active: true, currentWindow: true }, async ([tab]) => {
  if (!tab?.id) return;
  currentUrl = tab.url || "";
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const title = document.title.replace(/\s*[|\-].*$/, "").slice(0, 80);
        const body = document.body.innerText.slice(0, 4000);
        const pm = body.match(/(?:₹|Rs\.?)\s*([0-9,.]+)\s*(Cr|Crore|Lac|Lakh|L|k)?/i);
        let price = 0;
        if (pm) {
          const v = parseFloat(pm[1].replace(/,/g, ""));
          const u = (pm[2] || "").toLowerCase();
          price = u.startsWith("cr") ? v * 1e7 : (u.startsWith("l") ? v * 1e5 : (u === "k" ? v * 1e3 : v));
        }
        const sm = body.match(/(\d{3,4})\s*(?:sq\.?\s*ft|sqft)/i);
        return { title, price: Math.round(price), sqft: sm ? parseInt(sm[1], 10) : "" };
      }
    });
    $("name").value = result?.title || "";
    if (result?.price) {
      $("price").value = result.price;
      $("mode").value = result.price >= 2000000 ? "buy" : "rent";
    }
    if (result?.sqft) $("sqft").value = result.sqft;
  } catch {}
});

$("saveBtn").onclick = async () => {
  const name = $("name").value.trim(), price = Number($("price").value || 0);
  if (!name || price < 5000) { $("st").textContent = "Enter name & valid price"; return; }
  const src = currentUrl.includes("housing.com") ? "housing" : (currentUrl.includes("99acres") ? "99acres" : "other");
  $("st").textContent = "Saving...";
  try {
    const r = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name, locality: $("loc").value.trim() || "Mumbai", mode: $("mode").value,
        price_inr: price, carpet_sqft: Number($("sqft").value || 0) || null,
        url: currentUrl, source: src, zero_brokerage: false
      })
    });
    const d = await r.json();
    $("st").textContent = d.ok ? "Saved to Bombay Homes!" : (d.error || "Error saving");
  } catch {
    $("st").textContent = "Network error — check D1 binding";
  }
};
