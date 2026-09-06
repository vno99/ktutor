# Guide — Admin / Admin Guide

## Français

### Gérer les utilisateurs <a id="gerer-utilisateurs"></a>
L'administrateur accède au tableau de bord admin (`/dashboard/admin`) et aux endpoints `/users`. Il peut créer un utilisateur (`POST /users`), modifier son rôle (`PUT /users/{id}/role` : `admin`, `parent`, `eleve`), et lier parent-enfant. Toutes les requêtes filtrent par `student_pseudo` (multi-tenancy).

### Aperçu des flux étudiants <a id="apercu-flux"></a>
Les fonctionnalités principales sont couvertes dans le guide élève : création de compte, upload, chat, génération d'exercices, soumission de réponses, tableau de bord, et correction progressive (`< 80%` = indices, `≥ 80%` = correction complète, après 3 tentatives = correction complète dévoilée).

---

## English

### Manage users <a id="gerer-utilisateurs-en"></a>
The admin accesses the admin dashboard (`/dashboard/admin`) and `/users` endpoints. They can create a user (`POST /users`), update their role (`PUT /users/{id}/role`: `admin`, `parent`, `eleve`), and link parent-child. All queries filter by `student_pseudo` (multi-tenancy).

### Overview of student flows <a id="apercu-flux-en"></a>
Main features are covered in the student guide: account creation, upload, chat, exercise generation, answer submission, dashboard, and progressive correction (`< 80%` = hints, `≥ 80%` = full correction, after 3 attempts = full correction revealed).
