{ pkgs, ... }: {
  channel = "unstable";

  packages = [
    pkgs.hugo         # This installs Hugo
    pkgs.nodejs_20    # Node.js for PostCSS/Tailwind
  ];

  idx = {
    extensions = [
      "google.gemini-cli-vscode-ide-companion"
    ];
    previews = {
      enable = true;
      previews = {
        web = {
          command = ["hugo" "server" "--bind" "0.0.0.0" "--port" "$PORT" "-D"];
          manager = "web";
        };
      };
    };
    workspace = {
      onCreate = {
        default.openFiles = [ ".idx/dev.nix" "README.md" ];
      };
    };
  };
}
