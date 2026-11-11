package main

import (
	"os/exec"
	"sort"
	"strings"
	"testing"
)

// run builds nothing: it runs the package's main through `go run` so the test
// covers flag parsing and the exit code too.
func run(t *testing.T, args ...string) (string, int) {
	t.Helper()
	cmd := exec.Command("go", append([]string{"run", "."}, args...)...)
	out, err := cmd.Output()
	code := 0
	if e, ok := err.(*exec.ExitError); ok {
		code = e.ExitCode()
	} else if err != nil {
		t.Fatal(err)
	}
	return string(out), code
}

func TestGoodWorkflowPasses(t *testing.T) {
	out, code := run(t, "-private", "testdata/good")
	if code != 0 || out != "" {
		t.Fatalf("want no findings, got exit %d:\n%s", code, out)
	}
}

func TestBadWorkflowFindsEveryRule(t *testing.T) {
	out, code := run(t, "-private", "testdata/bad")
	if code != 1 {
		t.Fatalf("want exit 1, got %d", code)
	}
	rules := map[string]bool{}
	for _, l := range strings.Split(strings.TrimSpace(out), "\n") {
		parts := strings.SplitN(l, ": ", 3)
		if len(parts) >= 2 {
			rules[parts[1]] = true
		}
	}
	want := []string{"anonymous-github-download", "job-timeout", "permissions-top", "pin-actions", "required-check-paths", "runner-label", "setup-cache-self-hosted"}
	var got []string
	for r := range rules {
		got = append(got, r)
	}
	sort.Strings(got)
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Fatalf("rules:\n got  %v\n want %v\noutput:\n%s", got, want, out)
	}
}

func TestPublicRepoMayUseHostedRunners(t *testing.T) {
	out, _ := run(t, "testdata/bad")
	if strings.Contains(out, "ubuntu-latest: GitHub-hosted") {
		t.Fatalf("public repo flagged for a hosted runner:\n%s", out)
	}
}
