namespace GPV.ProductTimeFlow.Mobile.Services;

/// <summary>Error de validación local cuyo mensaje (en español) se muestra tal cual al usuario.</summary>
public sealed class UserFacingException(string message) : Exception(message);
