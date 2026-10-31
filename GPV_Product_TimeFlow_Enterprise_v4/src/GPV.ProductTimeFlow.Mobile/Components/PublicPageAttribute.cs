using System.Reflection;

namespace GPV.ProductTimeFlow.Mobile.Components;

/// <summary>Marca una página que se puede abrir sin sesión (inicio de sesión, ajustes del servidor).</summary>
[AttributeUsage(AttributeTargets.Class, Inherited = false)]
public sealed class PublicPageAttribute : Attribute
{
    public static bool IsPublic(Type pageType) => pageType.GetCustomAttribute<PublicPageAttribute>() is not null;
}
