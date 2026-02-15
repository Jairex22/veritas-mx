function login(){
    const user = document.getElementById("user").value;
    const pass = document.getElementById("pass").value;
    const role = document.getElementById("role").value;

    if(role === "student" && user === "alumno" && pass === "1234"){
        window.location.href = "dashboard.html";
    }
    else if(role === "admin" && user === "admin" && pass === "admin2026"){
        window.location.href = "admin.html";
    }
    else{
        alert("Credenciales incorrectas.");
    }
}
