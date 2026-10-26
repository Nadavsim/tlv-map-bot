# TLV Bot - how it fits together

Two diagrams, both written in Mermaid (GitHub renders them on this page).
Regenerate or edit them in any Mermaid editor; keep them in step with
`CLAUDE.md` when the architecture changes.

## System overview

Who touches what: the visitor's phone, the FastAPI app on Azure, the MongoDB
collections, the outside services, the curator's tooling and the build and
deploy pipeline. Dotted lines are optional, read-only or occasional.

```mermaid
flowchart TB
  subgraph Curator["The curator"]
    MyMaps["Google My Maps list<br/>167 pins, hand curated"]
    Scripts["Curator scripts<br/>show_reports, show_suggestions"]
  end

  subgraph Pipeline["Build and deploy"]
    Git["git push<br/>staging or main"]
    CI["GitHub Actions<br/>build, run tests"]
    Sync["Daily sync job<br/>4am UTC"]
    Monitor["UptimeRobot<br/>checks health on production"]
  end

  subgraph Phone["Visitor's phone: React app, installable PWA"]
    Start["Start screen and chat"]
    Cards["Result cards with sign plate<br/>distance, travel time"]
    MapView["Results map<br/>Leaflet"]
    Drawer["Menu: account, favorites,<br/>suggest a spot, saved addresses,<br/>settings, About, Privacy"]
  end

  subgraph Azure["Azure App Service: FastAPI backend"]
    Guards["Rate limits, input limits,<br/>text sanitiser, client-IP diagnostic"]
    Routes["API routes<br/>chat, more-places, etas, resolve-location,<br/>favorites, suggestions, reports, auth, health"]
    LLMsvc["LLM service<br/>Claude Haiku 4.5"]
    LocSvc["Location service<br/>Google-only link expansion,<br/>address lookup, street typo check"]
    RouteSvc["Routing service"]
    WxSvc["Weather service"]
  end

  subgraph Mongo["MongoDB Atlas, free tier"]
    Places[("places")]
    Users[("users and saved addresses")]
    Favs[("favorites")]
    Suggs[("place_suggestions<br/>deleted after 180 days")]
    Reports[("place_reports")]
    Stats[("category_stats and<br/>unmatched_queries")]
  end

  subgraph Ext["Outside services"]
    Claude["Anthropic Claude API"]
    OSRM["OSRM routing"]
    Nominatim["OpenStreetMap Nominatim"]
    Meteo["Open-Meteo weather"]
    GoogleMaps["Google Maps links"]
    GoogleSignIn["Google Sign-In"]
    Tiles["OpenStreetMap tiles"]
  end

  Start --> Guards
  Cards --> Guards
  Drawer --> Guards
  Guards --> Routes
  Routes --> LLMsvc
  Routes --> LocSvc
  Routes --> RouteSvc
  Routes --> WxSvc
  LLMsvc --> Claude
  LocSvc --> Nominatim
  LocSvc --> GoogleMaps
  RouteSvc --> OSRM
  WxSvc --> Meteo
  Drawer -. sign in .-> GoogleSignIn
  MapView -. map images .-> Tiles

  Routes --> Places
  Routes --> Users
  Routes --> Favs
  Routes --> Suggs
  Routes --> Reports
  Routes --> Stats

  MyMaps --> Sync
  Sync --> Places
  Scripts -. read only .-> Reports
  Scripts -. read only .-> Suggs
  Scripts -. flags near duplicates .-> Places
  Scripts --> MyMaps

  Git --> CI
  CI -->|tests pass| Azure
  Monitor -. health check .-> Routes
```

## What happens when someone asks for food

One chat message, from the craving to the travel time landing in the card.
The decisions in the middle are the honest-reply rules: a failed model call, a
request that is not about food, a requirement the list cannot honour, and a
place named in the message are each said out loud instead of hidden.

```mermaid
flowchart TD
  A(["Visitor sets a location,<br/>then types or taps a craving"]) --> B["Rate limit and length checks"]
  B --> C["Claude reads the message:<br/>category, tag, price, follow-up,<br/>unsupported requirement,<br/>outside food scope, named place"]
  C --> D{"Did the Claude call fail?"}
  D -->|yes| D1["Say: couldn't work that out just now<br/>Count it as llm_failed, log a warning"]
  D -->|no| E{"Not about food at all?<br/>for example a night club"}
  E -->|yes| E1["Say: my list only has food and coffee<br/>Log the text for the curator"]
  E -->|no| F{"Anything to search for?<br/>category, tag, price, surprise me,<br/>or a follow-up"}
  F -->|no| F1["Ask a clarifying question<br/>Log the text as unmatched"]
  F -->|yes| G["Find the nearest places<br/>in MongoDB from the set location"]
  G --> H["Put likely-closed places and<br/>rained-out patios after the rest"]
  H --> I{"Anything to say first?"}
  I -->|requirement the list can't honour| I1["Add: I don't have X marked<br/>Log the text for the curator"]
  I -->|a place named in the message| I2["Add: I search from the location you set<br/>not from that place"]
  I -->|no| J["Reply with the places"]
  I1 --> J
  I2 --> J
  J --> K["Cards appear at once<br/>with distance only"]
  K --> L["App asks for travel times<br/>OSRM, cached, stalls tolerated"]
  L --> M["Times settle into each<br/>sign plate"]
  K --> N["Visitor can: show more, open the map,<br/>share, navigate, save, report"]
```
