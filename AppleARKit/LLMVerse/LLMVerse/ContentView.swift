//
//  ContentView.swift
//  LLMVerse
//
//  Created by Chenuka Garusinghe on 10/12/2025.
//

import SwiftUI
import RealityKit
import Alamofire
import ZIPFoundation
import Foundation

func downloadZip(prompt: String) async throws -> URL {
    let destZip = FileManager.default.temporaryDirectory.appendingPathComponent("assets_bundle.zip")
    // clean any old copy
    if FileManager.default.fileExists(atPath: destZip.path) {
        try FileManager.default.removeItem(at: destZip)
    }

    let request = AF.download(
        "http://localhost:8000/generate",
        parameters: ["prompt": prompt],
        to: { _, _ in (destZip, [.removePreviousFile, .createIntermediateDirectories]) }
    )
    let _ = try await request.serializingDownloadedFileURL().value
    return destZip
}

func unzip(_ zipURL: URL) throws -> URL {
    let fm = FileManager.default
    let destDir = fm.temporaryDirectory.appendingPathComponent("unzipped", isDirectory: true)
    if fm.fileExists(atPath: destDir.path) { try fm.removeItem(at: destDir) }
    try fm.createDirectory(at: destDir, withIntermediateDirectories: true)
    try fm.unzipItem(at: zipURL, to: destDir)
    return destDir
}

func fileExtension(for url: URL) -> String {
    return url.pathExtension.lowercased()
}

func handleFilesAndInit(destZip: URL) -> [Entity: [SIMD3<Float>]] {
    do {
        let dirURL = try unzip(destZip)
        let contents = try FileManager.default.contentsOfDirectory(at: dirURL, includingPropertiesForKeys: nil, options: [])
        var meshDict: [Entity: [SIMD3<Float>]] = [:]

        for itemURL in contents {
            var isDirectory: ObjCBool = false
            if FileManager.default.fileExists(atPath: itemURL.path, isDirectory: &isDirectory), !isDirectory.boolValue {
                var entity: Entity? = nil
                var positions = [SIMD3<Float>]()
                let ext = fileExtension(for: itemURL)

                if ext == "usdz" {
                    entity = try? Entity.load(contentsOf: itemURL)
                } else if ext == "txt" {
                    let lines = try String(contentsOf: itemURL, encoding: .utf8).split(separator: "\n")
                    positions = lines.compactMap { line in
                        let coords = line.split(separator: ",").compactMap { Float($0.trimmingCharacters(in: .whitespaces)) }
                        return coords.count == 3 ? SIMD3<Float>(coords[0], coords[1], coords[2]) : nil
                    }
                }
                if let entity = entity {
                    meshDict[entity] = positions
                }
            }
        }
        return meshDict
    } catch {
        return [:]
    }
}

func addEntitiesToSession(Entity: Entity, positions: [SIMD3<Float>], AnchorEntity: AnchorEntity) -> Int{
    if positions == [] { return -1}
    for pos in positions {
        let entityInstance = Entity.clone(recursive: true)
        entityInstance.position = pos
        AnchorEntity.addChild(entityInstance)
    }
    return 0
}

struct ContentView : View {
    @State private var promptText: String = ""
    @State private var anchorsToAdd: [AnchorEntity] = []
    @State private var isLoading: Bool = false
    @State private var errorMessage: String?

    var body: some View {
        ZStack {
            RealityView { content in
                content.camera = .spatialTracking
            } update: { content in
                if !anchorsToAdd.isEmpty {
                    for anchor in anchorsToAdd {
                        content.add(anchor)
                    }
                    anchorsToAdd.removeAll()
                }
            }
            .edgesIgnoringSafeArea(.all)

            VStack {
                Spacer()
                HStack(spacing: 8) {
                    TextField("Describe what to generate", text: $promptText)
                        .textFieldStyle(.roundedBorder)
                        .disabled(isLoading)
                    if isLoading {
                        ProgressView()
                            .progressViewStyle(.circular)
                    }
                    Button {
                        Task {
                            await generateAndPrepareAnchors()
                        }
                    } label: {
                        Image(systemName: "paperplane.fill")
                            .imageScale(.large)
                            .padding(8)
                    }
                    .disabled(promptText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isLoading)
                }
                .padding(12)
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .padding()
            }
        }
        .alert("Error", isPresented: Binding(get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } })) {
            Button("OK", role: .cancel) { errorMessage = nil }
        } message: {
            Text(errorMessage ?? "")
        }
    }

    private func generateAndPrepareAnchors() async {
        await MainActor.run { isLoading = true }
        do {
            let zipPath = try await downloadZip(prompt: promptText)
            let arContentDict = handleFilesAndInit(destZip: zipPath)
            var newAnchors: [AnchorEntity] = []

            for (entity, positions) in arContentDict {
                let minExtent = Float.random(in: 0.2...0.6)
                let anchor = AnchorEntity(.plane(.horizontal, classification: .any, minimumBounds: SIMD2<Float>(minExtent, minExtent)))

                if addEntitiesToSession(Entity: entity, positions: positions, AnchorEntity: anchor) != -1 {
                    newAnchors.append(anchor)
                }
            }

            await MainActor.run {
                anchorsToAdd.append(contentsOf: newAnchors)
                promptText = ""
            }
        } catch {
            await MainActor.run {
                errorMessage = "Failed to download or initialize AR content: \(error)"
            }
        }
        await MainActor.run { isLoading = false }
    }
}

#Preview {
    ContentView()
}
