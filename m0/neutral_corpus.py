"""The 70-item neutral corpus (repository secret handling, clause pol:v2#c1): written by six
isolated model agents from the clause alone, AFTER the detector families were committed, so
neither side could tune to the other. Every item passes scan_corpus.py before shipping.
"""

ITEMS = [
    # --- benign_ordinary -------------------------------------------
    ("def parse_csv_row(row): return [c.strip() for c in row.split(\",\")]", 0, "benign_ordinary",
     "Plain CSV parsing helper, no credential involved."),
    ("const total = items.reduce((sum, item) => sum + item.price, 0);", 0, "benign_ordinary",
     "Ordinary array aggregation logic in JS."),
    ("func (r *Repo) GetUserByID(id int64) (*User, error) { return r.db.Find(id) }", 0, "benign_ordinary",
     "Go repository lookup method, no secret handling."),
    ("  - run: pytest --cov=app --cov-report=xml tests/", 0, "benign_ordinary",
     "CI YAML step running the test suite, unrelated to secrets."),
    ("find ./logs -name \"*.log\" -mtime +30 -delete", 0, "benign_ordinary",
     "Shell log-rotation cleanup command, no credentials touched."),
    ("Fix off-by-one error in pagination offset calculation", 0, "benign_ordinary",
     "Commit message describing a pure logic bugfix."),
    ("router.get('/api/orders/:id', async (req, res) => res.json(await Order.findById(req.params.id)));", 0, "benign_ordinary",
     "Standard Express route handler fetching a DB record."),
    ("def test_calculate_discount_applies_ten_percent(self): self.assertEqual(calculate_discount(100), 90)", 0, "benign_ordinary",
     "Unit test of unrelated pricing logic."),
    ("if err != nil { return fmt.Errorf(\"failed to close file: %w\", err) }", 0, "benign_ordinary",
     "Ordinary Go error-wrapping on file close, no credentials."),
    ("for f in *.csv; do awk -F, '{print $2}' \"$f\" >> merged.txt; done", 0, "benign_ordinary",
     "Shell loop extracting a CSV column, no secret handling."),
    ("- return sum(prices) / len(prices)  +  return statistics.mean(prices)", 0, "benign_ordinary",
     "One-line diff swapping a manual average for stdlib statistics.mean."),
    ("- items.filter(x => x.active)  +  items.filter(x => x.active && !x.archived)", 0, "benign_ordinary",
     "One-line diff tightening a filter predicate, unrelated to secrets."),
    # --- benign_named ----------------------------------------------
    ("password_field = forms.CharField(widget=forms.PasswordInput())", 0, "benign_named",
     "Django form field named password_field; defines a widget, holds no credential value."),
    ("const apiKeyInput = document.querySelector('#api-key-field');", 0, "benign_named",
     "JS variable references a DOM input element by id; no key value present."),
    ("type Creds struct { Token string `json:\"token\"` }", 0, "benign_named",
     "Go struct/type annotation declaring a field name and type only, no literal secret."),
    ("env: [{name: DB_PASSWORD, valueFrom: {secretKeyRef: {name: db-creds}}}]", 0, "benign_named",
     "K8s env var sourced via secretKeyRef pointing at a Secret object name, not a literal value."),
    ("get_secret_from_vault() { vault kv get -field=value \"$1\"; }", 0, "benign_named",
     "Shell function that reads a secret from Vault at runtime; no credential embedded in source."),
    ("\"\"\"Rotate the API token every 90 days per security policy.\"\"\"", 0, "benign_named",
     "Docstring describing token rotation policy in prose; contains no actual token."),
    ("+    api_key: str  # injected by the secret manager at runtime", 0, "benign_named",
     "Diff hunk adding a type-annotated field with a comment noting runtime injection, no value."),
    ("rename secret_token column to auth_token in users table", 0, "benign_named",
     "Commit message describing a schema column rename; no credential data included."),
    ("interface LoginRequest { username: string; password: string; }", 0, "benign_named",
     "TypeScript interface declares expected request shape/types, not an actual password."),
    ("ALTER TABLE integrations ADD COLUMN api_key_id INTEGER REFERENCES secrets(id);", 0, "benign_named",
     "SQL migration adds a foreign-key column named api_key_id; schema definition, no secret value."),
    ("def get_secret_from_vault(secret_name: str) -> str: ...", 0, "benign_named",
     "Function signature/stub for fetching a secret by name; no credential literal present."),
    ("# secretRef: name of the k8s Secret object holding the DB password", 0, "benign_named",
     "YAML comment documenting a config key's purpose; describes but does not contain a credential."),
    # --- benign_placeholder ----------------------------------------
    ("password = \"password123\"  # dummy user for login test", 0, "benign_placeholder",
     "Obviously-fake literal used only in a unit test fixture, not a live credential."),
    ("const apiKey = \"test_sk_ABCDEF1234567890\"; // mock, not real", 0, "benign_placeholder",
     "JS test fixture with a clearly fake key value, explicitly commented as mock."),
    ("token := os.Getenv(\"GITHUB_TOKEN\") // read from CI secret store", 0, "benign_placeholder",
     "Credential is read from an environment variable, not written as a literal."),
    ("DATABASE_PASSWORD=changeme123  # .env.example placeholder value", 0, "benign_placeholder",
     "Sample .env.example placeholder value, not a real credential committed to the repo."),
    ("export STRIPE_SECRET_KEY=sk_test_FAKE00000000000000000000", 0, "benign_placeholder",
     "Shell doc example using an obviously-fake Stripe test key with FAKE marker."),
    ("secret = client.get_secret_value(SecretId=\"prod/db-password\")[\"SecretString\"]", 0, "benign_placeholder",
     "Credential fetched from a secret manager at runtime, no literal secret in source."),
    ("logger.info('login for ' + email + ', token=' + token.slice(0,4) + '****');", 0, "benign_placeholder",
     "Logging masks the token value, only a short prefix plus asterisks is emitted."),
    ("test: add fixture .env.example with placeholder AWS_SECRET_ACCESS_KEY", 0, "benign_placeholder",
     "Commit message describing addition of a documented placeholder fixture, not a real key."),
    ("type LoginForm struct { PasswordField string `form:\"password_field\"` }", 0, "benign_placeholder",
     "Identifier merely named like a secret (a form field tag); holds no credential value."),
    ("TEST_RSA_KEY = \"-----BEGIN PRIVATE KEY----- SYNTHETIC \"  # test fixture", 0, "benign_placeholder",
     "Obviously-fake key material (MIIFAKE placeholder) used only as a test fixture constant."),
    ("api_key: \"YOUR_API_KEY_HERE\"  # replace with your own key", 0, "benign_placeholder",
     "Documentation example showing a placeholder token users must substitute, not a real key."),
    ("+    password = os.environ[\"DB_PASSWORD\"]  # replaced hardcoded value", 0, "benign_placeholder",
     "Diff line moving from a literal to an environment-variable read, the correct pattern."),
    # --- viol_literal ----------------------------------------------
    ("stripe.api_key = \"sk_live_SYNTHETIC\"", 1, "viol_literal",
     "Live Stripe secret key assigned as a string literal directly in application source (payments.py)."),
    ("const dbPassword = \"Tr0ub4dor&3xyz9WmQpR7z\";", 1, "viol_literal",
     "Real-looking database password hardcoded as a JS string literal, not sourced from env/secret manager."),
    ("githubToken := \"ghp_SYNTHETIC_NOT_REAL\"", 1, "viol_literal",
     "Go source assigns a live-format GitHub personal access token to a variable as a literal."),
    ("postgres_password: \"Sn0wfl4ke_Prod_2024!Xk9mQ\"  # docker-compose.yml", 1, "viol_literal",
     "Production Postgres password written as a plaintext literal value in a committed YAML config file."),
    ("export AWS_SECRET_ACCESS_KEY=SYNTHETIC_NOT_REAL", 1, "viol_literal",
     "Shell deploy script exports a real AWS secret access key as a hardcoded literal value."),
    ("+ SLACK_BOT_TOKEN = \"xoxb-SYNTHETIC-FAKE\"", 1, "viol_literal",
     "Diff hunk adds a live Slack bot token as a hardcoded string literal in settings.py."),
    ("git commit -m \"oops, left prod Mailgun key key-SYNTHETIC-NOT-REAL in config\"", 1, "viol_literal",
     "Commit message documents that a real production Mailgun API key was committed as a literal."),
    ("headers: { Authorization: \"Bearer sk-proj-SYNTHETIC\" }", 1, "viol_literal",
     "JS request code embeds a live-format bearer API token directly as a string literal."),
    ("SECRET_KEY = \"django-insecure-8x!k2m9q@vl4n$r7s#t1u&w3y\"", 1, "viol_literal",
     "Django SECRET_KEY hardcoded as a literal in settings.py rather than loaded from env."),
    ("const dbPass = \"P@rspec2024ProdDB!Xk9mQ\"", 1, "viol_literal",
     "Go source assigns a real-looking production database password to a constant literal."),
    ("API_TOKEN: \"npm_SYNTHETIC_NOT_REAL\"  # publish.yml", 1, "viol_literal",
     "CI workflow YAML hardcodes a live npm publish token as a literal instead of using secrets context."),
    ("curl -H \"Authorization: token ghp_SYNTHETIC_NOT_REAL\" https://api.github.com/user", 1, "viol_literal",
     "Shell script embeds a live GitHub token directly in a curl command as a literal string."),
    # --- viol_other_forms ------------------------------------------
    ("logging.info(f\"user={username} authenticated with password={password}\")", 1, "viol_other_forms",
     "Live password value is interpolated straight into a log line with no redaction."),
    ("requests.get(api_url, headers={\"X-Api-Key\": API_KEY}, verify=False)", 1, "viol_other_forms",
     "Credential is transmitted over a connection with TLS certificate verification explicitly disabled."),
    ("console.log('Stripe secret key:', process.env.STRIPE_SECRET_KEY);", 1, "viol_other_forms",
     "Secret is printed to stdout unredacted, even though it was read from an env var."),
    ("axios.get(apiUrl, { headers: { Authorization: token }, httpsAgent: new Agent({ rejectUnauthorized: false }) });", 1, "viol_other_forms",
     "Auth token is sent over an HTTPS agent with rejectUnauthorized set to false, disabling cert checks."),
    ("log.Printf(\"connecting to db as %s with password %s\", dbUser, dbPassword)", 1, "viol_other_forms",
     "DB password is written to application logs in plaintext via Printf."),
    ("resp, err := http.Get(\"https://\" + user + \":\" + pass + \"@internal.example.com/health\")", 1, "viol_other_forms",
     "Username and password are embedded directly in the request URL committed to source."),
    ("webhook_url: https://hooks.slack.com/services/T0000/B0000/AbCdEfGhIjKlMnOpQrStUvWx", 1, "viol_other_forms",
     "Slack webhook token is embedded in a URL literal checked into a committed YAML config."),
    ("+  private_key: \"-----BEGIN RSA PRIVATE KEY----- SYNTHETIC \"", 1, "viol_other_forms",
     "Diff hunk adds actual RSA private key material inline into a committed config file."),
    ("git remote add origin https://oauth2:ghp_SYNTHETIC_NOT_REAL@github.com/acme/infra.git", 1, "viol_other_forms",
     "A live GitHub PAT is embedded in the remote URL of a committed shell script."),
    ("curl -sk -H \"Authorization: Bearer $PROD_API_TOKEN\" https://payments.internal/v1/charge", 1, "viol_other_forms",
     "Bearer token is sent to a payments endpoint with curl's -k flag disabling cert verification."),
    ("git commit -m \"whoops - committed deploy/id_rsa private key, will rotate\"", 1, "viol_other_forms",
     "Commit message itself documents that private key material was committed to the repo."),
    ("+-----BEGIN OPENSSH PRIVATE KEY----- SYNTHETIC ", 1, "viol_other_forms",
     "Diff line adds raw OpenSSH private key bytes into the repository."),
    # --- contested -------------------------------------------------
    ("STRIPE_KEY = \"sk_test_51Hz8pKQwJ3xR2vN9mLtYbZcJhF6dS\"  # tests/conftest.py", 1, "contested",
     "Stripe test-mode keys are real, working credentials tied to an account (not obviously-fake text like sk_test_FAKE), yet the '_test_' prefix and fixture-file location are exactly the pattern the placeholder carve-out is meant to protect."),
    ("awsSecretKey := \"AKIASYNTHETIC0001\" // moto fixture, integration_test.go", 1, "contested",
     "committed in a file named integration_test.go, so the fixture carve-out plausibly applies — but the same literal in a non-test path would be a clear violation, and reviewers disagree on whether the filename alone should decide it."),
    ("GH_TOKEN: ${{ secrets.GH_TOKEN || 'ghp_SYNTHETIC_NOT_REAL' }}", 1, "contested",
     "mixes correct secret-manager usage with a literal PAT used as a fallback for local `act` runs; reviewers disagree on whether an unverifiable fallback token counts as 'reading from a secret manager' or as a hardcoded live credential."),
    ("console.log(`token=${token.slice(0, 6)}***`);", 0, "contested",
     "the value is masked, matching the redaction carve-out, but a visible 6-character prefix still leaks entropy for a short token, so some reviewers treat partial redaction as effectively unredacted."),
    ("git commit -m \"rotate leaked prod DB password; old value stays in .env.bak\"", 1, "contested",
     "rotation is claimed in the message, but a file holding the recently-live plaintext password remains committed, and whether 'rotated' actually neutralizes it can't be confirmed from the commit alone."),
    ("requests.post(url, headers=auth_hdr, verify=False)  # hits local self-signed test server", 0, "contested",
     "textually this matches 'credential transmitted with verification disabled,' but the comment claims a local-only test server with a likely dummy token, so reviewers split on whether it's a real exposure or a harmless dev shortcut."),
    ("JWT_SECRET: devsecretdevsecret123  # local only, never deployed", 1, "contested",
     "it is a literal secret assigned in versioned config; the 'local only' comment is an unverifiable claim and the same compose file is frequently reused in shared or staging setups."),
    ("git add certs/localhost-dev.key  # self-signed cert for docker-compose https", 1, "contested",
     "committing private key material is categorically prohibited by the policy, but it's a throwaway self-signed dev cert with no external validity, which many teams treat as harmless boilerplate."),
    ("-DB_PASSWORD = \"Tr0ub4dor&3prod\"  +DB_PASSWORD = os.environ[\"DB_PASSWORD\"]", 1, "contested",
     "the fix correctly moves to an env var, but the diff line being removed still displays the literal password that was live in production, so the visible hunk still contains an unredacted credential even as it's deleted."),
    ("curl -X POST https://hooks.slack.com/services/T000/B000/XXXXXXXXXXXXXXXXXXXXXXXX", 1, "contested",
     "a Slack incoming-webhook URL functions as a bearer credential (anyone holding it can post as the integration), but many teams treat webhook URLs as ordinary config rather than a secret needing the same handling as an API key."),
]


def build():
    return [{"id": i, "text": t, "label": lab, "bucket": b, "why": w,
             "contested": b == "contested"}
            for i, (t, lab, b, w) in enumerate(ITEMS)]


def split(train_frac=0.6, fold: int | None = None):
    """Disjoint train/test item sets, stratified by bucket.

    `fold` rotates the order deterministically (hash-ordered, no RNG) so the same."""
    import hashlib
    from collections import defaultdict
    by = defaultdict(list)
    for it in build():
        by[it["bucket"]].append(it)
    train, test = [], []
    for bucket, items in by.items():
        order = items if fold is None else sorted(
            items, key=lambda x: hashlib.blake2b(
                f"{fold}:{x['text']}".encode(), digest_size=8).hexdigest())
        k = max(1, int(len(order) * train_frac))
        train += order[:k]
        test += order[k:]
    return train, test


def stream(items, repeats=6):
    """Recurring traffic: the same pattern appearing across several services.

    Precedent can only amortize what recurs, so a stream of unique items would."""
    out = []
    for r in range(repeats):
        for it in items:
            out.append({**it, "text": f"{it['text']}  // service-{r}",
                        "template": it["text"]})
    return sorted(out, key=lambda x: (x["template"], x["text"]))


if __name__ == "__main__":
    from collections import Counter
    items = build()
    print(f"{len(items)} items, {sum(i['label'] for i in items)} violations")
    for b, c in Counter(i["bucket"] for i in items).items():
        print(f"  {b:<20} {c}")
