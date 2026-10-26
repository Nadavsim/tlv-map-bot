# TLV Bot - how it fits together

Three diagrams, written in Mermaid (GitHub renders them on this page). Edit
them in any Mermaid editor, and keep them in step with `CLAUDE.md` when the
architecture changes.

## What runs

The visitor's phone, the FastAPI app on Azure and its services, the MongoDB
collections, and the outside services it calls. Dotted lines are optional or
occasional.

```mermaid
flowchart LR
  subgraph Phone["Visitor's phone: React PWA"]
    Start["Start screen and chat"]
    Cards["Result cards with sign plate"]
    MapView["Results map"]
    Drawer["Menu: account,<br/>favorites, suggest a spot,<br/>saved addresses, settings"]
  end

  API["FastAPI app on Azure<br/>rate limits and text sanitiser<br/>chat, etas, favorites,<br/>suggestions, reports, auth"]

  subgraph Services["Backend services"]
    LLMsvc["LLM<br/>Claude Haiku 4.5"]
    LocSvc["Location<br/>Google-only links,<br/>address lookup, typo check"]
    RouteSvc["Routing"]
    WxSvc["Weather"]
  end

  subgraph Mongo["MongoDB Atlas"]
    Places[("places")]
    Users[("users, saved addresses")]
    Favs[("favorites")]
    Suggs[("place_suggestions<br/>deleted after 180 days")]
    Reports[("place_reports")]
    Stats[("usage stats,<br/>unmatched queries")]
  end

  subgraph Ext["Outside services"]
    Claude["Anthropic Claude API"]
    Nominatim["OpenStreetMap Nominatim"]
    GoogleMaps["Google Maps links"]
    OSRM["OSRM routing"]
    Meteo["Open-Meteo"]
    GoogleSignIn["Google Sign-In"]
    Tiles["OpenStreetMap tiles"]
  end

  Start --> API
  Cards --> API
  Drawer --> API
  Drawer -. sign in .-> GoogleSignIn
  MapView -. map images .-> Tiles

  API --> LLMsvc
  API --> LocSvc
  API --> RouteSvc
  API --> WxSvc
  LLMsvc --> Claude
  LocSvc --> Nominatim
  LocSvc --> GoogleMaps
  RouteSvc --> OSRM
  WxSvc --> Meteo

  API --> Places
  API --> Users
  API --> Favs
  API --> Suggs
  API --> Reports
  API --> Stats
```

## Who looks after it

The curator's list and scripts, the build and deploy pipeline, and the running
app they feed. Dotted lines are read-only or occasional.

```mermaid
flowchart TB
  subgraph Curator["The curator"]
    MyMaps["Google My Maps list<br/>167 pins, hand curated"]
    Scripts["Curator scripts<br/>show_reports, show_suggestions"]
  end

  subgraph Pipeline["Build and deploy"]
    Git["git push<br/>staging or main"]
    CI["GitHub Actions<br/>build and run tests"]
    Sync["Daily sync job<br/>4am UTC"]
  end

  subgraph Live["Running app"]
    Azure["Azure App Service<br/>staging and production"]
    Mongo[("MongoDB Atlas")]
    Monitor["UptimeRobot<br/>checks health on production"]
  end

  Git --> CI
  CI -->|tests pass| Azure
  MyMaps --> Sync
  Sync -->|places| Mongo
  Scripts -. reads reports and suggestions .-> Mongo
  Scripts -. add good ones by hand .-> MyMaps
  Monitor -. health check .-> Azure
```

## What happens when someone asks for food

One chat message, from the craving to the travel time landing in the card. The
decisions in the middle are the honest-reply rules: a failed model call, a
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
