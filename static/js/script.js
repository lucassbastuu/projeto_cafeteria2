document.querySelectorAll(".flash-close").forEach((button) => {
  button.addEventListener("click", () => {
    const flash = button.closest(".flash");
    if (flash) flash.remove();
  });
});

document.querySelectorAll("form[data-validate]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    const password = form.querySelector("[name=password]");
    const confirm = form.querySelector("[name=password_confirm]");
    const cup = form.querySelector("[name=cup_name]");
    let message = "";

    if (password && password.value.length < 8) {
      message = "A senha deve ter no mínimo 8 caracteres.";
    } else if (password && confirm && password.value !== confirm.value) {
      message = "As senhas não conferem.";
    } else if (cup) {
      const length = cup.value.trim().length;
      if (length < 2 || length > 30) {
        message = "O nome no copo deve ter entre 2 e 30 caracteres.";
      }
    }

    if (!message) return;

    event.preventDefault();
    let box = form.querySelector(".client-error");
    if (!box) {
      box = document.createElement("p");
      box.className = "client-error";
      box.setAttribute("role", "alert");
      form.prepend(box);
    }
    box.textContent = message;
  });
});
