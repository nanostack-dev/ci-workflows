// Command ci-lint checks a repository's GitHub Actions files against the
// organization's CI rules (docs/ci-principles.md). Each rule exists because
// breaking it caused an incident; the rule's doc string names it.
//
// Usage: ci-lint [-private] [-labels a,b,c] [dir]
//
// dir defaults to ".". It reads dir/.github/workflows/*.y{a,}ml and
// dir/.github/actions/**/action.y{a,}ml, prints one line per finding as
// file:line: rule: message, and exits 1 when there is any.
package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

type finding struct {
	file string
	line int
	rule string
	msg  string
}

// Runner labels a job may ask for. A label no runner carries queues the job
// forever; a GitHub-hosted label in a private repository bills the org (the
// 2026-10-13 spending-limit freeze).
var selfHosted = map[string]bool{
	"self-hosted": true, "nanostack-light": true, "nanostack-dev": true,
	"nanostack-dagger-pool": true, "nanostack-prod": true,
}

var hosted = regexp.MustCompile(`^(ubuntu|macos|windows)-`)

var shaRef = regexp.MustCompile(`@[0-9a-f]{40}$`)

func main() {
	private := flag.Bool("private", false, "repository is private: GitHub-hosted runners are not allowed")
	extra := flag.String("labels", "", "comma-separated extra runner labels to allow")
	flag.Parse()
	dir := "."
	if flag.NArg() > 0 {
		dir = flag.Arg(0)
	}
	for _, l := range strings.Split(*extra, ",") {
		if l = strings.TrimSpace(l); l != "" {
			selfHosted[l] = true
		}
	}

	var files []string
	for _, pat := range []string{".github/workflows/*.yml", ".github/workflows/*.yaml"} {
		m, _ := filepath.Glob(filepath.Join(dir, pat))
		files = append(files, m...)
	}
	_ = filepath.WalkDir(filepath.Join(dir, ".github/actions"), func(p string, d os.DirEntry, err error) error {
		if err == nil && !d.IsDir() && (d.Name() == "action.yml" || d.Name() == "action.yaml") {
			files = append(files, p)
		}
		return nil
	})
	sort.Strings(files)

	var out []finding
	for _, f := range files {
		raw, err := os.ReadFile(f)
		if err != nil {
			out = append(out, finding{f, 0, "read", err.Error()})
			continue
		}
		var doc yaml.Node
		if err := yaml.Unmarshal(raw, &doc); err != nil {
			out = append(out, finding{f, 0, "yaml", err.Error()})
			continue
		}
		if len(doc.Content) == 0 {
			continue
		}
		rel, _ := filepath.Rel(dir, f)
		out = append(out, check(rel, doc.Content[0], *private)...)
	}
	for _, x := range out {
		fmt.Printf("%s:%d: %s: %s\n", x.file, x.line, x.rule, x.msg)
	}
	if len(out) > 0 {
		fmt.Fprintf(os.Stderr, "%d finding(s). Rules: ci-workflows docs/ci-principles.md\n", len(out))
		os.Exit(1)
	}
}

func get(n *yaml.Node, key string) *yaml.Node {
	if n == nil || n.Kind != yaml.MappingNode {
		return nil
	}
	for i := 0; i+1 < len(n.Content); i += 2 {
		if n.Content[i].Value == key {
			return n.Content[i+1]
		}
	}
	return nil
}

func check(file string, root *yaml.Node, private bool) []finding {
	var out []finding
	add := func(n *yaml.Node, rule, msg string) {
		line := 0
		if n != nil {
			line = n.Line
		}
		out = append(out, finding{file, line, rule, msg})
	}
	isAction := strings.HasSuffix(file, "action.yml") || strings.HasSuffix(file, "action.yaml")

	// Every step, in jobs or in a composite action.
	var steps []*yaml.Node
	if isAction {
		if s := get(get(root, "runs"), "steps"); s != nil {
			steps = append(steps, s.Content...)
		}
	}

	if !isAction {
		// permissions-top: GITHUB_TOKEN starts with nothing; each job states what
		// it needs (tj-actions/changed-files compromise, 2025).
		if get(root, "permissions") == nil {
			add(root, "permissions-top", "set top-level `permissions: {}` (or read-only) and grant per job")
		}
		on := get(root, "on")
		hasCIOK := false
		jobs := get(root, "jobs")
		if jobs != nil {
			for i := 0; i+1 < len(jobs.Content); i += 2 {
				name, job := jobs.Content[i], jobs.Content[i+1]
				if name.Value == "ci-ok" || (get(job, "name") != nil && get(job, "name").Value == "ci-ok") {
					hasCIOK = true
				}
				if get(job, "uses") != nil {
					checkUses(get(job, "uses"), add)
					continue // a reusable workflow sets its own runner and timeout
				}
				// timeout: the default is 360 min; a hung job holds a slot that long.
				if get(job, "timeout-minutes") == nil {
					add(name, "job-timeout", "job "+name.Value+" has no timeout-minutes")
				}
				checkRunsOn(get(job, "runs-on"), private, add)
				if s := get(job, "steps"); s != nil {
					for _, st := range s.Content {
						st.Tag = "job:" + runsOnString(get(job, "runs-on"))
						steps = append(steps, st)
					}
				}
			}
		}
		// required-check-paths: a paths filter on pull_request makes a PR that
		// matches nothing get no ci-ok run, and a required ci-ok blocks it forever.
		if hasCIOK {
			if pr := get(on, "pull_request"); pr != nil {
				if p := get(pr, "paths"); p != nil {
					add(p, "required-check-paths", "workflow has ci-ok: remove `paths` from pull_request and gate jobs on a changes job")
				}
				if p := get(pr, "paths-ignore"); p != nil {
					add(p, "required-check-paths", "workflow has ci-ok: remove `paths-ignore` from pull_request")
				}
			}
		}
	}

	for _, st := range steps {
		if u := get(st, "uses"); u != nil {
			checkUses(u, add)
			// setup-cache-self-hosted: setup-go/setup-node tar caches restored into
			// the shared persistent caches of a self-hosted host collide
			// ("Cannot open: File exists", echopoint integration-drift 2026-11-10).
			if strings.HasPrefix(u.Value, "actions/setup-go@") || strings.HasPrefix(u.Value, "actions/setup-node@") {
				with := get(st, "with")
				c := get(with, "cache")
				selfHostedJob := strings.HasPrefix(st.Tag, "job:") && !hosted.MatchString(strings.TrimPrefix(st.Tag, "job:"))
				gated := c != nil && (c.Value == "false" || c.Value == "" || strings.Contains(c.Value, "github-hosted"))
				isGo := strings.HasPrefix(u.Value, "actions/setup-go@")
				// setup-go caches by default; setup-node only when `cache` is set.
				if (isAction || selfHostedJob) && !gated && (isGo || c != nil) {
					add(u, "setup-cache-self-hosted", "on a self-hosted runner set `cache: false` or `cache: ${{ runner.environment == 'github-hosted' }}`")
				}
			}
		}
		// anonymous-github-download: github.com throttles anonymous release
		// downloads in incidents (7 failed deploy-gate attempts, echopoint-cli
		// 2026-11-09). Send a token and retry.
		if r := get(st, "run"); r != nil {
			for i, l := range strings.Split(r.Value, "\n") {
				if (strings.Contains(l, "curl") || strings.Contains(l, "wget")) &&
					strings.Contains(l, "github.com/") && strings.Contains(l, "/releases/download/") &&
					!strings.Contains(r.Value, "Authorization") && !strings.Contains(r.Value, "GH_TOKEN") && !strings.Contains(r.Value, "GITHUB_TOKEN") {
					add(&yaml.Node{Line: r.Line + i + 1}, "anonymous-github-download", "download from github.com without a token; use `gh release download` or send GITHUB_TOKEN, with retries")
				}
			}
		}
	}
	return out
}

func checkUses(u *yaml.Node, add func(*yaml.Node, string, string)) {
	v := u.Value
	if strings.HasPrefix(v, "./") || strings.HasPrefix(v, "docker://") {
		return
	}
	// Reusable workflows of this org track main on purpose: one change reaches
	// every repository. Third-party code is pinned by commit, never by tag
	// (a moved tag dumped runner memory into logs in tj-actions/changed-files).
	if strings.HasPrefix(v, "nanostack-dev/") {
		return
	}
	if !shaRef.MatchString(v) {
		add(u, "pin-actions", v+": pin third-party actions to a full commit SHA")
	}
}

func runsOnString(n *yaml.Node) string {
	if n == nil {
		return ""
	}
	if n.Kind == yaml.ScalarNode {
		return n.Value
	}
	var parts []string
	for _, c := range n.Content {
		parts = append(parts, c.Value)
	}
	return strings.Join(parts, ",")
}

func checkRunsOn(n *yaml.Node, private bool, add func(*yaml.Node, string, string)) {
	if n == nil {
		return
	}
	var labels []*yaml.Node
	if n.Kind == yaml.ScalarNode {
		labels = []*yaml.Node{n}
	} else {
		labels = n.Content
	}
	for _, l := range labels {
		v := l.Value
		if strings.Contains(v, "${{") {
			continue // chosen by an expression; the caller's labels are checked there
		}
		switch {
		case hosted.MatchString(v):
			if private {
				add(l, "runner-label", v+": GitHub-hosted runners are not allowed in private repositories (billing freeze 2026-10-13)")
			}
		case !selfHosted[v]:
			add(l, "runner-label", v+": no runner carries this label; use nanostack-light, nanostack-dev, nanostack-dagger-pool or nanostack-prod")
		}
	}
}
