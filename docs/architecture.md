# TLV Bot - how it fits together

Six diagrams, written in Mermaid (GitHub renders them on this page). Edit
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

## Code map: which file talks to which

For someone reading the code for the first time. Solid arrows are imports or calls; the thick arrow is the only network hop between the two halves. `App.tsx` owns all state; everything under `components/` receives props and calls back up.

```mermaid
flowchart TB
  subgraph FE["frontend/src (React + TypeScript)"]
    main["main.tsx<br/>ErrorBoundary + App"]
    App["App.tsx<br/>all state and handlers"]
    Header["Header.tsx"]
    Side["SideMenu.tsx"]
    Acct["AccountSection.tsx<br/>GoogleSignInButton, SuggestSpot"]
    Log["ChatLog.tsx<br/>ChatBubble, TypingIndicator"]
    LocForm["LocationForm.tsx"]
    Cards["PlaceCards.tsx<br/>ShareButton, MapView (lazy)"]
    Card["PlaceCard.tsx<br/>CategoryIcon"]
    Input["ChatInput.tsx"]
    API["api.ts<br/>one function per endpoint"]
    Support["types.ts, chatTypes.ts,<br/>i18n.ts, preferences.ts, share.ts"]
  end

  subgraph BE["backend/ (FastAPI, Python)"]
    app["app.py<br/>routes, middleware,<br/>rate limits, reply text"]
    models["models.py<br/>Pydantic schema"]
    db["db.py<br/>every MongoDB query"]
    parser["parser.py<br/>KML to Place"]
    subgraph Svc["services/"]
      llm["llm.py"]
      loc["location.py<br/>streets.py"]
      route["routing.py<br/>resilience.py"]
      wx["weather.py"]
      auth["auth.py"]
      sug["suggestions.py"]
      cip["clientip.py"]
    end
  end

  subgraph Scripts["scripts/ (run by hand or GitHub Actions)"]
    sync["sync_places.py"]
    rep["show_reports.py"]
    shows["show_suggestions.py"]
  end

  main --> App
  App --> Header --> Side --> Acct
  App --> Log --> Cards --> Card
  Log --> LocForm
  App --> Input
  App --> API
  Card --> API
  LocForm --> API
  App -.-> Support
  API == "HTTP /api/*" ==> app
  app --> llm
  app --> loc
  app --> route
  app --> wx
  app --> auth
  app --> sug
  app --> cip
  app --> db
  db --> models
  parser --> models
  sync --> parser
  sync --> db
  rep --> db
  shows --> db
  sug --> loc
```

## Code path of one chat message

Function-level trace of the main feature, from `handleSend` to the travel times landing. Results come back first with distance only; the times are a second request so a slow routing service never delays the cards.

```mermaid
sequenceDiagram
  autonumber
  actor V as Visitor
  participant App as App.tsx<br/>handleSend
  participant API as api.ts
  participant R as app.py<br/>chat()
  participant L as llm.py<br/>parse_food_request
  participant D as db.py
  participant W as weather.py
  participant Q as app.py<br/>etas()
  participant O as routing.py

  V->>App: types or taps a craving
  App->>App: getPreviousContext() reads last results entry
  App->>API: postChat(message, lat, lon, lang, previous_*)
  API->>R: POST /api/chat
  R->>D: get_categories(), get_dietary_tags()
  R->>L: parse_food_request(message, known lists)
  L-->>R: category, tag, price, is_followup, flags
  alt LLM failed, out of scope or nothing to search
    R->>D: record_category_request(), log_unmatched_query()
    R-->>App: reply text only
  else something to search
    R->>D: find_nearest(category, lat, lon, tag, price)
    D->>W: is_raining_now()
    D-->>R: places sorted by distance, likely-closed last
    R-->>App: reply + places (distance only, eta null)
  end
  App->>V: bubble, then cards arrive
  App->>API: postEtas(origin, mode, destinations)
  API->>Q: POST /api/etas
  Q->>O: get_eta_seconds_batch()
  O-->>Q: durations (cached, timeout 3s)
  Q-->>App: formatted times
  App->>V: times settle into each card
```

## From a tap to the database

Eight common actions, each traced from the control the visitor touches to the handler, the route in `backend/app.py`, and the function that does the work. Every route that touches stored user data needs the bearer token.

```mermaid
flowchart LR
  subgraph U["User action"]
    a1["Type an address or paste a link"]
    a2["Tap Live"]
    a3["Tap Show more"]
    a4["Tap the heart"]
    a5["Report a place"]
    a6["Sign in with Google"]
    a7["Suggest a spot"]
    a8["Save an address"]
  end

  subgraph H["Frontend: component and handler"]
    h1["LocationForm<br/>resolveLocation()"]
    h2["App.requestLocation()<br/>navigator.geolocation"]
    h3["App.handleShowMore()"]
    h4["App.handleToggleFavorite()"]
    h5["PlaceCard<br/>postPlaceReport()"]
    h6["GoogleSignInButton to<br/>App.handleGoogleCredential()"]
    h7["SuggestSpot to<br/>App.handleSuggestSpot()"]
    h8["App.handleSaveAddress()"]
  end

  subgraph R["Backend route in app.py"]
    r1["POST /api/resolve-location"]
    r2["no server call"]
    r3["POST /api/more-places"]
    r4["POST or DELETE<br/>/api/favorites"]
    r5["POST /api/place-reports"]
    r6["POST /api/auth/google"]
    r7["POST /api/suggestions"]
    r8["POST /api/saved-addresses"]
  end

  subgraph S["Service or db function"]
    s1["location.resolve_maps_link_detail,<br/>geocode_address, streets.suggest_correction"]
    s2["Coordinates go straight<br/>into App state"]
    s3["db.find_nearest<br/>from the original origin"]
    s4["db.add_favorite,<br/>db.remove_favorite"]
    s5["db.record_place_report"]
    s6["auth.verify_google_id_token,<br/>db.create_user, create_access_token"]
    s7["suggestions.clean_text and is_google_link,<br/>db.add_suggestion"]
    s8["db.add_saved_address"]
  end

  a1 --> h1 --> r1 --> s1
  a2 --> h2 --> r2 --> s2
  a3 --> h3 --> r3 --> s3
  a4 --> h4 --> r4 --> s4
  a5 --> h5 --> r5 --> s5
  a6 --> h6 --> r6 --> s6
  a7 --> h7 --> r7 --> s7
  a8 --> h8 --> r8 --> s8
```
