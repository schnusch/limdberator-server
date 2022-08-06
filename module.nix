{ config, lib, pkgs, ... }:

with lib;

let
  cfg = config.services.limdberator;

  listenStream =
    if cfg.address == null then
      [ "[::1]:${toString cfg.port}" "127.0.0.1:${toString cfg.port}" ]
    else if hasInfix "/" cfg.address then
      [ cfg.address ]
    else if hasInfix ":" cfg.address then
      [ "[${cfg.address}]:${toString cfg.port}" ]
    else
      [ "${cfg.address}:${toString cfg.port}" ]
    ;

  nginxProxyAddress =
    if hasInfix "/" (head listenStream) then
      "unix:${head listenStream}:"
    else
      head listenStream
    ;
in
{

  options = {
    services.limdberator = {
      enable = mkEnableOption "LIMDberator server";

      package = mkOption {
        type = types.package;
        default = pkgs.python3.pkgs.callPackage ./. {};
        defaultText = literalExpression "pkgs.python3.pkgs.callPackage ./. {}";
        description = "The LIMDberator server package to use.";
      };

      address = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = ''
          The IP address or socket path on which LIMDberator will listen.
          By default listens on localhost.
        '';
        example = "/run/limdberator/socket";
      };

      port = mkOption {
        type = types.port;
        default = 8080;
        description = "The port on which LIMDberator will listen";
      };

      nginx = mkOption {
        default = {};
        description = ''
          Configuration for nginx reverse proxy.
        '';

        type = types.submodule {
          options = {
            enable = mkOption {
              type = types.bool;
              default = false;
              description = ''
                Configure the nginx reverse proxy settings.
              '';
            };

            hostName = mkOption {
              type = types.str;
              description = ''
                The hostname to use to setup the virtualhost configuration
              '';
            };

            path = mkOption {
              type = types.str;
              default = "/";
              description = ''
                The path to use to setup the virtualhost configuration
              '';
            };
          };
        };
      };

    };

  };

  config = mkIf cfg.enable (
    mkMerge [
      {
        meta.maintainers = with lib.maintainers; [ schnusch ];

        systemd.sockets.limdberator = {
          wantedBy = [ "sockets.target" ];
          socketConfig.ListenStream = listenStream;
        };

        systemd.services.limdberator = {
          description = "LIMDberator server";
          serviceConfig = {
            User = "limdberator";
            Group = "limdberator";
            DynamicUser = "yes";
            RuntimeDirectory = "limdberator";
            StateDirectory = "limdberator";
            StateDirectoryMode = "0755";
            PrivateDevices = true;
            # Sandboxing
            CapabilityBoundingSet = "CAP_NET_RAW CAP_NET_ADMIN";
            ProtectSystem = "strict";
            ProtectHome = true;
            PrivateTmp = true;
            ProtectKernelTunables = true;
            ProtectKernelModules = true;
            ProtectControlGroups = true;
            RestrictAddressFamilies = "AF_INET AF_INET6 AF_UNIX AF_PACKET AF_NETLINK";
            RestrictNamespaces = true;
            LockPersonality = true;
            MemoryDenyWriteExecute = true;
            RestrictRealtime = true;
            RestrictSUIDSGID = true;
            ExecStart = ''
              ${cfg.package}/bin/limdberator \
                --database /var/lib/limdberator/limdberator.db \
                --systemd
            '';
          };
        };
      }

      (
        mkIf cfg.nginx.enable {
          services.nginx = {
            enable = true;
            virtualHosts."${cfg.nginx.hostName}" = {
              locations."= ${cfg.nginx.path}" = {
                proxyPass = "http://${nginxProxyAddress}/";
              };
            };
          };
        }
      )
    ]
  );
}
