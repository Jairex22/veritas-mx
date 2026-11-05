# Evidencia de pruebas (C#)

Fecha: 2026-11-05 · Linux, .NET SDK 10.0.114 · Comando: `dotnet test`

**Resultado: 125 pruebas, 0 fallos.**

## Equivalencia con la versión Python

Se ejecutaron ambas versiones en paralelo (modo demo) y se compararon 21 llamadas a la API (trazabilidad Mirion, fallo parcial, errores 401/500/timeout/JSON inválido, sin registros, Pulse, Quality + tiempos de cierre, Rework por unidad y batch, historial, configuración, diagnóstico, entradas inválidas):

- Mismos códigos HTTP y misma estructura JSON en 20/21; la única diferencia es intencional (`connect_timeout_seconds` nuevo en `/api/diagnostics`).
- Caso Mirion W07632100028: `state`, `summary`, `header`, `defects`, `timeline`, `evidence` y la secuencia de alertas (R02, R03, R05, R04, R06, R08, R09) **idénticos** entre Python y C#.

## Recorrido en navegador (Chromium headless, 1366×900 y 390×844)

Dashboard → escaneo + Enter → Trazabilidad → Pulse → Quality + tiempos de cierre → Rework → DEMO-QH-FAIL → DEMO-ERR-500 → Diagnóstico ($metadata) → Configuración (guardar) → tema oscuro → descarga XLSX. 0 errores de consola; 0 errores en el log.

## Defecto encontrado y corregido durante las pruebas

`AppConfig.Num()` no leía números enteros creados en memoria; un valor entero guardado desde la pantalla Configuración se habría ignorado o habría provocado error. Corregido (`AppConfig.TryNumber`) y cubierto por `ConfigNumericTests`.

## Lista de pruebas

```
  Passed Gpv.Sqi.Tests.CacheTests.DedupBetweenWindows
  Passed Gpv.Sqi.Tests.CacheTests.DemoAndLiveNeverMixed
  Passed Gpv.Sqi.Tests.CacheTests.EmptyGuidNotUsedAsKey
  Passed Gpv.Sqi.Tests.CacheTests.HistorySameDefectNotOverwritten
  Passed Gpv.Sqi.Tests.CacheTests.WindowQueryUsesUtc
  Passed Gpv.Sqi.Tests.ConfigNumericTests.NumReadsInMemoryAndParsedValues
  Passed Gpv.Sqi.Tests.ConfigTests.ExampleConfigLoads
  Passed Gpv.Sqi.Tests.ConfigTests.Limits
  Passed Gpv.Sqi.Tests.ConfigTests.OverridesApplyAndInvalidIgnored
  Passed Gpv.Sqi.Tests.ConfigTests.PasswordInConfigRejected
  Passed Gpv.Sqi.Tests.ConfigTests.SecurityFlagsNotEditable(key: "odata.password")
  Passed Gpv.Sqi.Tests.ConfigTests.SecurityFlagsNotEditable(key: "security.allow_basic_auth_over_http")
  Passed Gpv.Sqi.Tests.ConfigTests.SecurityFlagsNotEditable(key: "security.live_mode_approved")
  Passed Gpv.Sqi.Tests.DefectTests.ClosedWithoutClosureHistory
  Passed Gpv.Sqi.Tests.DefectTests.DefectIdCaseInsensitive
  Passed Gpv.Sqi.Tests.DefectTests.HistoryRowsNeverCountedAsDefects
  Passed Gpv.Sqi.Tests.DefectTests.HistoryUnavailableMarksIncomplete
  Passed Gpv.Sqi.Tests.DefectTests.MirionFodCountedOnce
  Passed Gpv.Sqi.Tests.DefectTests.NullsTolerated
  Passed Gpv.Sqi.Tests.DefectTests.OpenAndUnknown
  Passed Gpv.Sqi.Tests.DefectTests.TimeToCloseComputed
  Passed Gpv.Sqi.Tests.FailureModeTests.AllSourcesFailIsErrorNotEmpty(id: "DEMO-ERR-401")
  Passed Gpv.Sqi.Tests.FailureModeTests.AllSourcesFailIsErrorNotEmpty(id: "DEMO-ERR-403")
  Passed Gpv.Sqi.Tests.FailureModeTests.AllSourcesFailIsErrorNotEmpty(id: "DEMO-ERR-500")
  Passed Gpv.Sqi.Tests.FailureModeTests.AllSourcesFailIsErrorNotEmpty(id: "DEMO-INVALID-JSON")
  Passed Gpv.Sqi.Tests.FailureModeTests.AllSourcesFailIsErrorNotEmpty(id: "DEMO-TIMEOUT")
  Passed Gpv.Sqi.Tests.FailureModeTests.EmptyIsNotFound
  Passed Gpv.Sqi.Tests.FailureModeTests.InvalidIdentifierRejected(bad: "   ")
  Passed Gpv.Sqi.Tests.FailureModeTests.InvalidIdentifierRejected(bad: "")
  Passed Gpv.Sqi.Tests.FailureModeTests.InvalidIdentifierRejected(bad: "<script>")
  Passed Gpv.Sqi.Tests.FailureModeTests.InvalidIdentifierRejected(bad: "A B")
  Passed Gpv.Sqi.Tests.FailureModeTests.InvalidIdentifierRejected(bad: "A'B")
  Passed Gpv.Sqi.Tests.FailureModeTests.InvalidIdentifierRejected(bad: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"···)
  Passed Gpv.Sqi.Tests.FailureModeTests.NonStringIdentifierRejected
  Passed Gpv.Sqi.Tests.FailureModeTests.QualityHistoryFailureDoesNotHideSmt
  Passed Gpv.Sqi.Tests.FailureModeTests.TimeoutUsesLastValidCacheMarkedStale
  Passed Gpv.Sqi.Tests.FilterTests.ControlCharsAndLength
  Passed Gpv.Sqi.Tests.FilterTests.EscapeQuotes
  Passed Gpv.Sqi.Tests.FilterTests.FieldMustExistInMetadata
  Passed Gpv.Sqi.Tests.FilterTests.FullUrlShape
  Passed Gpv.Sqi.Tests.FilterTests.InOperatorLimited
  Passed Gpv.Sqi.Tests.FilterTests.InjectionAttemptStaysInsideLiteral
  Passed Gpv.Sqi.Tests.FilterTests.TopBounds(top: 0)
  Passed Gpv.Sqi.Tests.FilterTests.TopBounds(top: 5000)
  Passed Gpv.Sqi.Tests.FilterTests.TypedLiterals
  Passed Gpv.Sqi.Tests.FilterTests.UnauthorizedFieldEntityOperator
  Passed Gpv.Sqi.Tests.FrontendStaticTests.AllReferencedIdsExist
  Passed Gpv.Sqi.Tests.FrontendStaticTests.ApiRoutesUsedExist
  Passed Gpv.Sqi.Tests.FrontendStaticTests.NoInlineScriptsOrHandlers
  Passed Gpv.Sqi.Tests.FrontendStaticTests.NoPassLabelInUi
  Passed Gpv.Sqi.Tests.FrontendStaticTests.NoUnsafeDomSinks
  Passed Gpv.Sqi.Tests.FrontendStaticTests.SidebarHasNineSections
  Passed Gpv.Sqi.Tests.LogSanitizeTests.Sanitize
  Passed Gpv.Sqi.Tests.MetadataTests.ParseFixture
  Passed Gpv.Sqi.Tests.MetadataTests.RejectsDoctypeAndGarbage(xml: "<?xml version=\"1.0\"?><!DOCTYPE x
  Passed Gpv.Sqi.Tests.MetadataTests.RejectsDoctypeAndGarbage(xml: "<root/>")
  Passed Gpv.Sqi.Tests.MetadataTests.RejectsDoctypeAndGarbage(xml: "not xml")
  Passed Gpv.Sqi.Tests.MetadataTests.V3Detection
  Passed Gpv.Sqi.Tests.MirionAcceptanceTests.FodOnceAoiNotTwoBoards
  Passed Gpv.Sqi.Tests.MirionAcceptanceTests.Header
  Passed Gpv.Sqi.Tests.MirionAcceptanceTests.MergedSources
  Passed Gpv.Sqi.Tests.MirionAcceptanceTests.NeverPass
  Passed Gpv.Sqi.Tests.MirionAcceptanceTests.RepairAndClosedShown
  Passed Gpv.Sqi.Tests.MirionAcceptanceTests.ReportGenerated
  Passed Gpv.Sqi.Tests.ModulesDemoTests.PulseExcludesHistoricalFixture
  Passed Gpv.Sqi.Tests.ModulesDemoTests.PulseFilterAndShiftErrors
  Passed Gpv.Sqi.Tests.ModulesDemoTests.QualityUniqueDefects
  Passed Gpv.Sqi.Tests.ModulesDemoTests.ReworkBatch
  Passed Gpv.Sqi.Tests.ODataClientTests.AuthErrorsNotRetried(code: 401, expected: AUTH_ERROR)
  Passed Gpv.Sqi.Tests.ODataClientTests.AuthErrorsNotRetried(code: 403, expected: FORBIDDEN)
  Passed Gpv.Sqi.Tests.ODataClientTests.BasicAuthHeaderSentAndNotLogged
  Passed Gpv.Sqi.Tests.ODataClientTests.ConcurrencyLimitSerializesRequests
  Passed Gpv.Sqi.Tests.ODataClientTests.ConnectionRefused
  Passed Gpv.Sqi.Tests.ODataClientTests.DnsFailure
  Passed Gpv.Sqi.Tests.ODataClientTests.EmptyIsDistinctFromError
  Passed Gpv.Sqi.Tests.ODataClientTests.EntityMissingInMetadata
  Passed Gpv.Sqi.Tests.ODataClientTests.InvalidJsonAndStructure(body: "<html>500</html>")
  Passed Gpv.Sqi.Tests.ODataClientTests.InvalidJsonAndStructure(body: "{\"items\":
  Passed Gpv.Sqi.Tests.ODataClientTests.InvalidJsonAndStructure(body: "{\"value\": \"x\"}")
  Passed Gpv.Sqi.Tests.ODataClientTests.MetadataFailureFallsBackAndMarksUnverified
  Passed Gpv.Sqi.Tests.ODataClientTests.MissingCredentials
  Passed Gpv.Sqi.Tests.ODataClientTests.NoAuthHeaderWhenNone
  Passed Gpv.Sqi.Tests.ODataClientTests.NotFound404
  Passed Gpv.Sqi.Tests.ODataClientTests.OkWithRows
  Passed Gpv.Sqi.Tests.ODataClientTests.PaginationForeignOriginIgnored
  Passed Gpv.Sqi.Tests.ODataClientTests.PaginationSameOrigin
  Passed Gpv.Sqi.Tests.ODataClientTests.PolicyBlocks
  Passed Gpv.Sqi.Tests.ODataClientTests.RateLimited429
  Passed Gpv.Sqi.Tests.ODataClientTests.RedirectNotFollowed
  Passed Gpv.Sqi.Tests.ODataClientTests.ResultsEmittedForAudit
  Passed Gpv.Sqi.Tests.ODataClientTests.Server500RetriedWithBackoffThenFails
  Passed Gpv.Sqi.Tests.ODataClientTests.Server503ThenSuccess
  Passed Gpv.Sqi.Tests.ODataClientTests.TimeoutNotRetried
  Passed Gpv.Sqi.Tests.ParserTests.EmptyValueIsValid
  Passed Gpv.Sqi.Tests.ParserTests.InvalidJson
  Passed Gpv.Sqi.Tests.ParserTests.NullValuesPreserved
  Passed Gpv.Sqi.Tests.ParserTests.UnexpectedStructures(raw: "[]")
  Passed Gpv.Sqi.Tests.ParserTests.UnexpectedStructures(raw: "{\"d\":\"text\"}")
  Passed Gpv.Sqi.Tests.ParserTests.UnexpectedStructures(raw: "{\"error\":{\"message\":\"x\"}}")
  Passed Gpv.Sqi.Tests.ParserTests.UnexpectedStructures(raw: "{\"items\":[]}")
  Passed Gpv.Sqi.Tests.ParserTests.UnexpectedStructures(raw: "{\"value\":[1,2]}")
  Passed Gpv.Sqi.Tests.ParserTests.UnexpectedStructures(raw: "{\"value\":{}}")
  Passed Gpv.Sqi.Tests.ParserTests.V2ResultsAndNext
  Passed Gpv.Sqi.Tests.ParserTests.V4Value
  Passed Gpv.Sqi.Tests.ReportTests.Csv
  Passed Gpv.Sqi.Tests.ReportTests.HtmlEscapes
  Passed Gpv.Sqi.Tests.ReportTests.XlsxIsValidOoxml
  Passed Gpv.Sqi.Tests.ReworkTests.ConfirmedLoopOnlyWithAuthorizedFlow
  Passed Gpv.Sqi.Tests.ReworkTests.DuplicateEvent
  Passed Gpv.Sqi.Tests.ReworkTests.MirionRules
  Passed Gpv.Sqi.Tests.ReworkTests.NoAlertsForCleanFlow
  Passed Gpv.Sqi.Tests.ServerTests.ApiRequiresCsrf
  Passed Gpv.Sqi.Tests.ServerTests.BadInput400
  Passed Gpv.Sqi.Tests.ServerTests.BodyLimit
  Passed Gpv.Sqi.Tests.ServerTests.ConfigCannotEnableSecurityFlags
  Passed Gpv.Sqi.Tests.ServerTests.Diagnostics
  Passed Gpv.Sqi.Tests.ServerTests.DnsRebindingHostRejected
  Passed Gpv.Sqi.Tests.ServerTests.ForeignOriginRejected
  Passed Gpv.Sqi.Tests.ServerTests.IndexHasCspAndToken
  Passed Gpv.Sqi.Tests.ServerTests.ReportDownload
  Passed Gpv.Sqi.Tests.ServerTests.StaticAndTraversal
  Passed Gpv.Sqi.Tests.ServerTests.StatusAndTrace
  Passed Gpv.Sqi.Tests.TimelineTests.ChronologicalAndNullsLast
  Passed Gpv.Sqi.Tests.TimelineTests.DefectCountedOnceInTimeline
  Passed Gpv.Sqi.Tests.TimelineTests.MixedOffsetsSortedByInstant
```
