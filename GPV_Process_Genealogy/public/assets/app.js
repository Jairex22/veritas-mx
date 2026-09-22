"use strict";

/**
 * GPV Process Genealogy - frontend application.
 *
 * Written as plain JavaScript using React.createElement directly (no
 * JSX, no bundler, no build step). React/ReactDOM are loaded as global
 * UMD builds from /vendor before this file, so this script can run
 * exactly as-is in the browser once node/index.js serves it - nothing
 * here needs compiling.
 *
 * This file is the canonical source. public/assets/app.js is an
 * identical copy served by the app (see README.txt).
 */

(function () {
  const h = React.createElement;
  const useState = React.useState;
  const useCallback = React.useCallback;

  const LEVEL_ORDER = ["SMT", "HM", "MS", "MS1"];

  const STATUS_LABELS = {
    COMPLETED: "COMPLETED",
    CURRENT: "CURRENT",
    NEXT: "NEXT",
    BLOCKED: "BLOCKED",
    "NOT STARTED": "NOT STARTED",
  };

  function statusSlug(status) {
    return String(status || "")
      .toLowerCase()
      .replace(/\s+/g, "-");
  }

  // ---------------------------------------------------------------------
  // Small presentational helpers
  // ---------------------------------------------------------------------
  function StatusBadge(props) {
    const status = props.status || "NOT STARTED";
    return h(
      "span",
      { className: "badge badge-" + statusSlug(status) },
      STATUS_LABELS[status] || status
    );
  }

  function RouteArrow() {
    return h("div", { className: "route-arrow", "aria-hidden": "true" }, "→");
  }

  // ---------------------------------------------------------------------
  // Navbar
  // ---------------------------------------------------------------------
  function Navbar() {
    return h(
      "header",
      { className: "navbar" },
      h(
        "div",
        { className: "navbar-left" },
        h("span", { className: "navbar-badge" }, "GPV"),
        h("span", { className: "navbar-title" }, "PROCESS GENEALOGY")
      ),
      h(
        "div",
        { className: "navbar-right" },
        h("span", { className: "status-dot" }),
        h("span", { className: "navbar-status-label" }, "LOCAL DATA")
      )
    );
  }

  // ---------------------------------------------------------------------
  // Search bar
  // ---------------------------------------------------------------------
  function SearchBar(props) {
    const value = props.value;
    const onChange = props.onChange;
    const onSubmit = props.onSubmit;

    return h(
      "form",
      {
        className: "search-panel",
        onSubmit: function (e) {
          e.preventDefault();
          onSubmit();
        },
      },
      h("h2", { className: "search-title" }, "Search Assembly"),
      h(
        "div",
        { className: "search-row" },
        h("input", {
          className: "search-input",
          type: "text",
          placeholder: "Enter assembly number or part number...",
          value: value,
          onChange: function (e) {
            onChange(e.target.value);
          },
          "aria-label": "Assembly search",
        }),
        h("button", { className: "search-button", type: "submit" }, "SEARCH")
      )
    );
  }

  function SearchMessage(props) {
    if (!props.state) return null;
    if (props.state === "found") {
      return h("div", { className: "search-message search-message-found" }, "✓ Assembly found");
    }
    if (props.state === "notfound") {
      return h("div", { className: "search-message search-message-notfound" }, "Assembly not found");
    }
    return null;
  }

  // ---------------------------------------------------------------------
  // Empty state (no search yet)
  // ---------------------------------------------------------------------
  function EmptyState() {
    return h(
      "div",
      { className: "empty-state" },
      h("h1", { className: "empty-state-title" }, "GPV Process Genealogy"),
      h(
        "p",
        { className: "empty-state-subtitle" },
        "Search an assembly to visualize its manufacturing route."
      ),
      h(
        "div",
        { className: "empty-diagram" },
        LEVEL_ORDER.map(function (level, idx) {
          return h(
            React.Fragment,
            { key: level },
            idx > 0 ? h(RouteArrow, { key: level + "-arrow" }) : null,
            h("div", { className: "empty-diagram-chip" }, level)
          );
        })
      )
    );
  }

  // ---------------------------------------------------------------------
  // Assembly information card
  // ---------------------------------------------------------------------
  function InfoField(props) {
    return h(
      "div",
      { className: "info-field" },
      h("span", { className: "info-label" }, props.label),
      h("span", { className: "info-value" }, props.value === undefined || props.value === null || props.value === "" ? "—" : props.value)
    );
  }

  function AssemblyInfoCard(props) {
    const a = props.assembly;
    const previousLevel = props.previousLevel;
    const nextLevel = props.nextLevel;

    return h(
      "section",
      { className: "card assembly-info-card" },
      h("h2", { className: "card-title" }, "ASSEMBLY INFORMATION"),
      h(
        "div",
        { className: "info-grid" },
        h(InfoField, { label: "Assembly", value: a.assembly }),
        h(InfoField, { label: "Part Number", value: a.partNumber }),
        h(InfoField, { label: "Description", value: a.description }),
        h(InfoField, { label: "Work Order", value: a.workOrder }),
        h(InfoField, { label: "Current Level", value: a.currentLevel }),
        h(InfoField, { label: "Previous Level", value: previousLevel }),
        h(InfoField, { label: "Next Level", value: nextLevel }),
        h(InfoField, { label: "Status", value: a.status })
      ),
      h(
        "div",
        { className: "progress-block" },
        h("div", { className: "info-label" }, "Progress"),
        h(
          "div",
          { className: "progress-bar-track" },
          h("div", {
            className: "progress-bar-fill",
            style: { width: Math.max(0, Math.min(100, Number(a.progress) || 0)) + "%" },
          })
        ),
        h("div", { className: "progress-value" }, (Number(a.progress) || 0) + "%")
      ),
      h(
        "div",
        { className: "route-summary" },
        h("span", { className: "info-label" }, "Route: "),
        h("span", { className: "info-value" }, (a.route || []).join(" → "))
      )
    );
  }

  // ---------------------------------------------------------------------
  // Genealogy tree (SMT -> HM -> MS -> MS1)
  // ---------------------------------------------------------------------
  function LevelCard(props) {
    const level = props.level;
    const isSelected = props.isSelected;
    return h(
      "button",
      {
        type: "button",
        className: "level-card" + (isSelected ? " level-card-selected" : ""),
        onClick: function () {
          props.onSelect(level.id);
        },
      },
      h("div", { className: "level-card-name" }, level.name),
      h(StatusBadge, { status: level.status })
    );
  }

  function GenealogyTree(props) {
    const levels = props.levels;
    const selectedLevelId = props.selectedLevelId;

    return h(
      "section",
      { className: "card genealogy-card" },
      h("h2", { className: "card-title" }, "PROCESS GENEALOGY"),
      h(
        "div",
        { className: "genealogy-tree" },
        levels.map(function (level, idx) {
          return h(
            React.Fragment,
            { key: level.id },
            idx > 0 ? h(RouteArrow, { key: level.id + "-arrow" }) : null,
            h(LevelCard, {
              level: level,
              isSelected: level.id === selectedLevelId,
              onSelect: props.onSelectLevel,
            })
          );
        })
      )
    );
  }

  // ---------------------------------------------------------------------
  // Selected level detail + stations
  // ---------------------------------------------------------------------
  function formatTime(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (isNaN(date.getTime())) return value;
    const pad = function (n) {
      return String(n).padStart(2, "0");
    };
    return (
      date.getFullYear() +
      "-" +
      pad(date.getMonth() + 1) +
      "-" +
      pad(date.getDate()) +
      " " +
      pad(date.getHours()) +
      ":" +
      pad(date.getMinutes()) +
      ":" +
      pad(date.getSeconds())
    );
  }

  function StationRow(props) {
    const s = props.station;
    return h(
      "tr",
      { className: "station-row" },
      h("td", { className: "station-seq" }, String(s.sequence).padStart(2, "0")),
      h("td", { className: "station-name" }, s.name),
      h("td", null, h(StatusBadge, { status: s.status })),
      h("td", { className: "station-time" }, formatTime(s.startTime)),
      h("td", { className: "station-time" }, formatTime(s.endTime)),
      h("td", { className: "station-time" }, s.duration || "—")
    );
  }

  function LevelDetailPanel(props) {
    const level = props.level;
    const assembly = props.assembly;
    if (!level) {
      return h(
        "section",
        { className: "card level-detail-card" },
        h("p", { className: "muted" }, "Select a level above to see its route and stations.")
      );
    }

    const stations = level.stations || [];

    return h(
      "section",
      { className: "card level-detail-card" },
      h("h2", { className: "card-title" }, "SELECTED LEVEL"),
      h(
        "div",
        { className: "level-detail-header" },
        h("div", { className: "level-detail-name" }, level.name),
        h(StatusBadge, { status: level.status })
      ),
      h(
        "div",
        { className: "info-grid" },
        h(InfoField, { label: "Level", value: level.id }),
        h(InfoField, { label: "Work Order", value: assembly.workOrder }),
        h(InfoField, { label: "Assembly", value: assembly.assembly }),
        h(InfoField, { label: "Description", value: assembly.description }),
        h(InfoField, { label: "Previous level", value: level.previousLevel || "—" }),
        h(InfoField, { label: "Next level", value: level.nextLevel || "—" }),
        h(InfoField, { label: "Stations", value: stations.length })
      ),
      h("h3", { className: "subsection-title" }, "ROUTE / STATIONS"),
      h(
        "div",
        { className: "stations-table-wrap" },
        h(
          "table",
          { className: "stations-table" },
          h(
            "thead",
            null,
            h(
              "tr",
              null,
              h("th", null, "#"),
              h("th", null, "Station"),
              h("th", null, "Status"),
              h("th", null, "Start"),
              h("th", null, "End"),
              h("th", null, "Duration")
            )
          ),
          h(
            "tbody",
            null,
            stations.map(function (s) {
              return h(StationRow, { key: s.sequence, station: s });
            })
          )
        )
      )
    );
  }

  // ---------------------------------------------------------------------
  // Genealogy relations (parent / child assemblies)
  // ---------------------------------------------------------------------
  function GenealogyRelations(props) {
    const parent = props.parentAssembly;
    const children = props.childAssemblies || [];
    const onNavigate = props.onNavigate;

    if (!parent && children.length === 0) {
      return h(
        "section",
        { className: "card relations-card" },
        h("h2", { className: "card-title" }, "RELATED ASSEMBLIES"),
        h(
          "p",
          { className: "muted" },
          "No parent or child assemblies are linked for this record in the demo data."
        )
      );
    }

    return h(
      "section",
      { className: "card relations-card" },
      h("h2", { className: "card-title" }, "RELATED ASSEMBLIES"),
      parent
        ? h(
            "div",
            { className: "relation-block" },
            h("div", { className: "info-label" }, "Parent assembly"),
            h(
              "button",
              {
                type: "button",
                className: "relation-link",
                onClick: function () {
                  onNavigate(parent.assembly);
                },
              },
              parent.description + " — " + parent.assembly
            )
          )
        : null,
      children.length > 0
        ? h(
            "div",
            { className: "relation-block" },
            h("div", { className: "info-label" }, "Child assemblies"),
            h(
              "ul",
              { className: "relation-list" },
              children.map(function (c) {
                return h(
                  "li",
                  { key: c.assembly },
                  h(
                    "button",
                    {
                      type: "button",
                      className: "relation-link",
                      onClick: function () {
                        onNavigate(c.assembly);
                      },
                    },
                    c.description + " — " + c.assembly
                  )
                );
              })
            )
          )
        : null
    );
  }

  // ---------------------------------------------------------------------
  // App
  // ---------------------------------------------------------------------
  function App() {
    const state = useState("");
    const query = state[0];
    const setQuery = state[1];

    const assemblyState = useState(null);
    const assembly = assemblyState[0];
    const setAssembly = assemblyState[1];

    const searchStatusState = useState(null); // null | 'found' | 'notfound'
    const searchStatus = searchStatusState[0];
    const setSearchStatus = searchStatusState[1];

    const selectedLevelState = useState(null);
    const selectedLevelId = selectedLevelState[0];
    const setSelectedLevelId = selectedLevelState[1];

    const errorState = useState(null);
    const loadError = errorState[0];
    const setLoadError = errorState[1];

    const runSearch = useCallback(
      function (term) {
        const q = (term === undefined ? query : term).trim();
        if (!q) return;
        setLoadError(null);
        fetch("/api/assemblies/" + encodeURIComponent(q))
          .then(function (res) {
            if (res.status === 404) {
              setAssembly(null);
              setSelectedLevelId(null);
              setSearchStatus("notfound");
              return null;
            }
            if (!res.ok) {
              throw new Error("Request failed with status " + res.status);
            }
            return res.json();
          })
          .then(function (data) {
            if (!data) return;
            setAssembly(data);
            setSelectedLevelId(data.currentLevel || (data.levels[0] && data.levels[0].id) || null);
            setSearchStatus("found");
          })
          .catch(function (err) {
            setLoadError(String(err && err.message ? err.message : err));
            setSearchStatus(null);
          });
      },
      [query]
    );

    const navigateTo = useCallback(
      function (assemblyId) {
        setQuery(assemblyId);
        runSearch(assemblyId);
      },
      [runSearch]
    );

    const selectedLevel =
      assembly && selectedLevelId
        ? (assembly.levels || []).find(function (l) {
            return l.id === selectedLevelId;
          })
        : null;

    const previousLevelName =
      assembly && selectedLevel && selectedLevel.previousLevel ? selectedLevel.previousLevel : assembly ? "—" : null;
    const nextLevelName =
      assembly && selectedLevel && selectedLevel.nextLevel ? selectedLevel.nextLevel : assembly ? "—" : null;

    return h(
      "div",
      { className: "app-shell" },
      h(Navbar, null),
      h(
        "main",
        { className: "app-main" },
        h(SearchBar, {
          value: query,
          onChange: setQuery,
          onSubmit: function () {
            runSearch();
          },
        }),
        h(SearchMessage, { state: searchStatus }),
        loadError
          ? h("div", { className: "search-message search-message-notfound" }, "Error: " + loadError)
          : null,
        !assembly
          ? h(EmptyState, null)
          : h(
              React.Fragment,
              null,
              h(AssemblyInfoCard, {
                assembly: assembly,
                previousLevel: selectedLevel ? selectedLevel.previousLevel : assembly.levels[0] && assembly.levels[0].previousLevel,
                nextLevel: selectedLevel ? selectedLevel.nextLevel : null,
              }),
              h(GenealogyTree, {
                levels: assembly.levels || [],
                selectedLevelId: selectedLevelId,
                onSelectLevel: setSelectedLevelId,
              }),
              h(LevelDetailPanel, { level: selectedLevel, assembly: assembly }),
              h(GenealogyRelations, {
                parentAssembly: assembly.parentAssembly,
                childAssemblies: assembly.childAssemblies,
                onNavigate: navigateTo,
              })
            )
      ),
      h(
        "footer",
        { className: "app-footer" },
        "GPV Process Genealogy — DEMO DATA (local prototype, not connected to FactoryLogix)"
      )
    );
  }

  const root = ReactDOM.createRoot(document.getElementById("root"));
  root.render(h(App, null));
})();
