// Mock search: reads ?q=, ranks a fixed index by keyword overlap, renders results with textContent.
(function () {
  "use strict";

  var INDEX = [
    { title: "Kalpana Chawla - The Open Encyclopedia", url: "article.html",
      display: "encyclopedia.example/wiki/Kalpana_Chawla",
      snippet: "Kalpana Chawla (1962-2003) was an Indian-born American astronaut and aerospace engineer, born in Karnal, India. She was the first woman of Indian origin to go to space.",
      keywords: "kalpana chawla astronaut born birthplace karnal india nasa space columbia woman engineer" },
    { title: "Kalpana Chawla biography for kids", url: "article.html#early-life",
      display: "encyclopedia.example/wiki/Kalpana_Chawla#Early_life",
      snippet: "Early life: Kalpana Chawla grew up in Karnal and studied aeronautical engineering at Punjab Engineering College.",
      keywords: "kalpana chawla early life karnal school college childhood born" },
    { title: "Disability Pension Portal - Apply online", url: "../portal/index.html",
      display: "localhost/portal",
      snippet: "Apply for the monthly disability pension. You need your Aadhaar number, bank account and IFSC code.",
      keywords: "disability pension portal apply government scheme welfare" },
    { title: "Accessible Store - aids for daily living", url: "shop.html",
      display: "localhost/web/shop",
      snippet: "White canes, talking watches and braille books, delivered to your door.",
      keywords: "shop buy store white cane talking watch braille order online shopping" },
    { title: "MockMail - your inbox", url: "inbox.html",
      display: "localhost/web/inbox",
      snippet: "Read your latest mail.",
      keywords: "mail email inbox gmail my mail messages" },
  ];
  var AD = { title: "Ad: Space-themed gifts, 50% off today", url: "shop.html", display: "localhost/web/shop",
    snippet: "Sponsored. Limited time offer on astronaut toys.", keywords: "space astronaut nasa kalpana chawla" };

  function words(s) { return (s.toLowerCase().match(/[a-z0-9]+/g) || []).filter(function (w) { return w.length > 1; }); }

  function score(entry, qWords) {
    var kw = words(entry.keywords + " " + entry.title);
    return qWords.filter(function (w) { return kw.indexOf(w) !== -1; }).length;
  }

  function render(entry, isAd) {
    var li = document.createElement("li");
    li.className = "result" + (isAd ? " ad" : "");
    var h2 = document.createElement("h2");
    var a = document.createElement("a");
    a.href = entry.url;
    a.textContent = entry.title;
    h2.appendChild(a);
    var url = document.createElement("div");
    url.className = "url";
    url.textContent = entry.display;
    var snippet = document.createElement("p");
    snippet.className = "snippet";
    snippet.textContent = entry.snippet;
    li.append(h2, url, snippet);
    return li;
  }

  var q = (new URLSearchParams(location.search).get("q") || "").trim();
  document.getElementById("q").value = q;
  if (!q) return;
  document.title = q + " at MockSearch";

  var qWords = words(q);
  var hits = INDEX.map(function (e) { return { e: e, s: score(e, qWords) }; })
    .filter(function (h) { return h.s > 0; })
    .sort(function (a, b) { return b.s - a.s; });

  var list = document.getElementById("results");
  var summary = document.getElementById("summary");
  if (!hits.length) {
    summary.textContent = "No results found for \"" + q + "\".";
    return;
  }
  // A sponsored result sits above the organic ones when it matches, like real search pages.
  if (score(AD, qWords) > 0) list.appendChild(render(AD, true));
  hits.forEach(function (h) { list.appendChild(render(h.e, false)); });
  summary.textContent = hits.length + " results for \"" + q + "\"";
})();
