;; linux, the kernel for a Dojo machine booted from an initramfs.
;; linux 7.3, the latest release on 2026-10-27, matching linux-headers. Written by hand.

;; Built in, since the kernel loads no modules: what a QEMU or KVM guest needs to reach its
;; initramfs, console, disk and network, then what a PC like smk-1 needs (DOJ-33): its NVMe or
;; SATA disk, its Realtek or Intel wired NIC, USB sticks and keyboards, a GPT disk booted by
;; UEFI, and the firmware's framebuffer as a console. The RTL8125A's firmware patch is left out:
;; r8169 runs without it.
(local builtin [:BLK_DEV_INITRD
                :RD_GZIP
                :DEVTMPFS
                :DEVTMPFS_MOUNT
                :SERIAL_8250
                :SERIAL_8250_CONSOLE
                :VIRTIO_MENU
                :VIRTIO
                :VIRTIO_PCI
                :VIRTIO_BLK
                :VIRTIO_NET
                :VIRTIO_CONSOLE
                :HW_RANDOM_VIRTIO
                :NET_CORE
                :ETHERNET
                :NET_VENDOR_INTEL
                :E1000
                :PACKET
                :UNIX
                :INET
                :BLK_DEV_NVME
                :ATA
                :SATA_AHCI
                :NET_VENDOR_REALTEK
                :R8169
                :IGB
                :USB_XHCI_HCD
                :USB_XHCI_PCI
                :USB_STORAGE
                :USB_UAS
                :USB_HID
                :EFI_STUB
                :EFI_PARTITION
                :DRM_EFIDRM
                :DRM_FBDEV_EMULATION
                :FRAMEBUFFER_CONSOLE])

{:name :linux
 :origin :karate
 :version :7.3
 :targets [:x86_64-linux]
 :maintainer "Strip Mall Karate Company"
 :license [:gplv2]
 :description "The Linux kernel"
 :upstream_url "https://www.kernel.org/"
 :source {:url "https://www.kernel.org/pub/linux/kernel/v7.x/linux-7.3.tar.xz"
          :sha256 :87363c24f10e06321eb362765521094e94471f6bff8bce2d6b3e40f39f004953
          :dirname :linux-7.3}
 :build_deps [:karate/bc
              :karate/bison
              :karate/flex
              :karate/diffutils
              :karate/elfutils
              :karate/zlib
              :karate/findutils
              :karate/gcc
              :karate/gcc-libs
              :karate/make
              :karate/perl
              :karate/openssl
              :karate/gzip
              :karate/pkg-config]
 :build (fn [b]
          ;; Host programs (objtool, extract-cert) link the build dependencies' libraries and
          ;; run during the build, so they carry those libraries' directories. sorttable's threads
          ;; make glibc open libgcc_s itself, which only an old-style RPATH reaches.
          (b:env :HOSTCFLAGS (or (b:getenv :CFLAGS) ""))
          (b:env :HOSTLDFLAGS
                 (.. (or (b:getenv :LDFLAGS) "")
                     " -Wl,--disable-new-dtags,-rpath,"
                     (table.concat (icollect [_ dep (ipairs [:elfutils
                                                             :openssl
                                                             :zlib
                                                             :gcc-libs])]
                                     (.. (b:path_for dep) :/lib))
                                   ":")))
          ;; The same kernel from the same source, whoever builds it.
          (b:env :KBUILD_BUILD_USER :dojo)
          (b:env :KBUILD_BUILD_HOST :dojo)
          (b:env :KBUILD_BUILD_TIMESTAMP :1970-01-01)
          (b:run [:make :mrproper])
          (b:run [:make :x86_64_defconfig])
          (let [args [:scripts/config
                      :--disable
                      :MODULES
                      :--disable
                      :DEBUG_INFO
                      :--enable
                      :DEBUG_INFO_NONE]]
            (each [_ opt (ipairs builtin)]
              (table.insert args :--enable)
              (table.insert args opt))
            (b:run args))
          (b:run [:make :olddefconfig])
          (b:run [:make :-j (tostring b.jobs) :bzImage]))
 :install (fn [b]
            (b:mkdir (b:join b.prefix :boot))
            (b:copy (b:join b.src :arch/x86/boot/bzImage)
                    (b:join b.prefix :boot/bzImage))
            (b:copy (b:join b.src :.config) (b:join b.prefix :boot/config)))}
