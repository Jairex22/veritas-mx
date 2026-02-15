function responder(correcto){
    const resultado = document.getElementById("resultado");

    if(correcto){
        resultado.innerText = "Respuesta Correcta ✅";
        resultado.style.color = "#00FF9D";
    } else {
        resultado.innerText = "Respuesta Incorrecta ❌";
        resultado.style.color = "red";
    }
}
